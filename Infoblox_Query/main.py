from requests import Response, Session
from configparser import ConfigParser

from functools import partial
import urllib3
import json
import re

# Typing shenanigans

import typing as t

JSON_Values = t.Union[str, int, float, bool, None]
HTTP_METHODS = t.Literal["GET", "POST", "PUT"]
STATUS = t.Literal["USED", "UNUSED"]
# TODO: Add more specitivity to the various attributes


class VLAN(t.TypedDict):
    value: t.Optional[str]


class NETWORK(t.TypedDict):
    _ref: str
    network: str
    network_view: str
    extattrs: VLAN


class IPV4ADDRESS(t.TypedDict):
    _ref: str
    ip_address: str
    is_conflict: bool
    mac_address: str
    names: t.List[str]
    network: str
    network_view: str
    objects: t.List[str]
    status: STATUS
    types: t.List[str]
    usage: t.List[str]


# Plumbing
# Disable certificate warnings and get the configuration from the config file
urllib3.disable_warnings()

config = ConfigParser()
config.read(filenames="infoblox_setup.cfg")

Info_User = config["infoblox"]["USER"]
Info_Pass = config["infoblox"]["PASS"]
Info_Host = config["infoblox"]["HOST"]

Info_URL = f"https://{Info_Host}/wapi/v2.2/"


class RestClient:
    """The requests library handles mantaining a session alive and cookies for
    us.

    This class is a simple namespace to get that sorted out for us
    """

    _session: t.Optional[Session] = None

    @classmethod
    def PrepareSession(cls) -> Session:
        cls._session = Session()
        cls._session.auth = (Info_User, Info_Pass)
        cls._session.verify = False
        return cls._session

    @classmethod
    def GetSession(cls) -> Session:
        if cls._session:
            return cls._session

        return cls.PrepareSession()


def InfoGet(
    query: t.Dict[str, t.Any], url: str, method: HTTP_METHODS = "GET"
) -> Response:
    request = partial(
        RestClient.GetSession().request,
        method,
        f"{Info_URL}{url}",
        params=query,
    )
    try:
        return request()
    except ConnectionResetError:
        """If we're making too many requests the server might reset the
        connection. If so we try again but don't catch any further
        Exceptions, if they appear that means we have problems
        """
        RestClient.PrepareSession()
        return request()


def slugify(value: str) -> str:
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value


def InfoBoxPagination(
    url: str, params: t.Dict[str, t.Any] = {}, method: HTTP_METHODS = "GET"
) -> t.Iterable[t.List[t.Dict[str, JSON_Values]]]:
    """ Simple HTTP request that handles Infobox's pagination for us! """
    # Initial request
    response = InfoGet(
        {
            **params,
            "_paging": 1,
            "_return_as_object": 1,
            # Infoblox breaks when there's more than 100
            "_max_results": 100,
        },
        url,
        method,
    ).json()

    yield response.get("result")

    next_page = response.get("next_page_id")

    while next_page:
        res_json = InfoGet({"_page_id": next_page}, url).json()
        yield res_json["result"]
        # We use get here so we don't worry about silly KeyExceptions
        next_page = res_json.get("next_page_id")


def add_network_ignore_voip(
    results: t.List[NETWORK],
    json_res: t.List[NETWORK],
) -> None:
    """ Adds networks we care about to some json_res!"""

    def filter_good_res(network: NETWORK) -> bool:
        """We only care about networks that aren't VoIP"""
        view = network.get("network_view")
        return True if (view and "voip" not in view.lower()) else False

    json_res.extend(filter(filter_good_res, results))


def get_all_networks() -> None:
    """
    Get all of the network ranges we're interested in
    By get, I mostly mean save to a file in `data/networks.json`
    """
    json_res: t.List[NETWORK] = []
    for page in InfoBoxPagination(
        "network", {"_return_fields": ["network", "extattrs", "network_view"]}
    ):
        add_network_ignore_voip(t.cast(t.List[NETWORK], page), json_res)

    with open("data/networks.json", "w") as f:
        f.write(str(json_res))

    print("All done!")


def iterate_through_network() -> None:
    with open("data/networks.json") as f:

        networks = json.load(f)
        for network in networks:
            print("Checking out:", network["network"])
            json_res: t.List[IPV4ADDRESS] = []
            for res in InfoBoxPagination(
                "ipv4address",
                {
                    "network": network["network"],
                    "network_view": network["network_view"],
                },
            ):
                if type(res) == list:
                    json_res.extend(t.cast(t.List[IPV4ADDRESS], res))
                else:
                    json_res.append(t.cast(IPV4ADDRESS, res))
            # Save data to some file
            file_name = (
                f"data/ips_{network['network'].replace('/', '_to_')}.json"
            )
            with open(file_name, "w") as f:
                json.dump(json_res, f, ensure_ascii=False, indent=2)
                print("Written results in: ", file_name)


if __name__ == "__main__":
    # get_all_networks()
    iterate_through_network()
