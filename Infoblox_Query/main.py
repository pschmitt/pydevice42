import json
import typing as t
from configparser import ConfigParser
from functools import partial

import urllib3
from requests import RequestException, Response, Session

# Use this magnificent library to convert a request to a curl string!
# Super useful for testing purposes
# import curlify
# from pprint import pprint


"""-------------------- Typing shenanigans  --------------------"""


JSON_Values = t.Union[str, int, float, bool, None]
HTTP_METHODS = t.Literal["GET", "POST", "PUT"]
STATUS = t.Literal["USED", "UNUSED"]
T = t.TypeVar("T")
# TODO: Add more specitivity to the various attributes


"""-------------------- Infoblox Related Types --------------------"""


class ExtraInfo(t.TypedDict):
    # ATTENTION
    # Value is either just an str-able int; or two hyphen separated ints!
    # TODO:
    value: str


class ExtAttrs(t.TypedDict, total=False):
    VLAN: ExtraInfo
    Site: ExtraInfo


class NETWORKBASE(t.TypedDict):
    _ref: str
    network: str
    network_view: str


class NETWORK(NETWORKBASE, total=False):
    comment: str
    extattrs: ExtAttrs


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


"""-------------------- Device42 Related Types --------------------"""


class VlanD42(t.TypedDict, total=False):
    number: str
    name: str
    description: str
    notes: str
    vlan_id: str


class SubnetD42(t.TypedDict):
    network: str
    mask_bits: str
    name: str
    description: str
    notes: str


class RestClient:
    """The requests library handles mantaining a session alive and cookies for
    us.

    This class is a simple namespace to get that sorted out for us
    """

    def __init__(self, username: str, password: str, host: str) -> None:
        self._username = username
        self._password = password
        self._host = host
        self._session: t.Optional[Session] = None

    def prepareSession(self) -> Session:
        s = Session()
        s.auth = (self._username, self._password)
        s.verify = False
        self._session = s
        return self._session

    def session(self) -> Session:
        if self._session:
            return self._session
        return self.prepareSession()

    def request(
        self,
        url: str,
        query: t.Optional[t.Dict[str, t.Any]] = None,
        json_data: t.Optional[t.Dict[str, t.Any]] = None,
        data: t.Optional[t.Dict[str, t.Any]] = None,
        method: HTTP_METHODS = "GET",
    ) -> Response:
        request = partial(
            self.session().request,
            method,
            f"{self._host}{url}",
            params=query,
            json=json_data,
        )
        try:
            return request()
        except ConnectionResetError:
            """
            If we're making too many requests the server might reset the
            connection. If so we try again but don't catch any further
            Exceptions, if they appear that means we have problems
            """
            self.prepareSession()
            return request()


# Plumbing
# Disable certificate warnings and get the configuration from the config file
urllib3.disable_warnings()

# Get the Config Settings
config = ConfigParser()
config.read(filenames="infoblox_setup.cfg")

Info_User = config["infoblox"]["USER"]
Info_Pass = config["infoblox"]["PASS"]
Info_Host = config["infoblox"]["HOST"]

D42_User = config["d42"]["USER"]
D42_Pass = config["d42"]["PASS"]
D42_Host = config["d42"]["HOST"]


InfoBloxClient = RestClient(Info_User, Info_Pass, Info_Host)
D42Client = RestClient(D42_User, D42_Pass, D42_Host)

"""-------------------- Infoblox Methods --------------------"""


def InfoBoxPagination(
    url: str,
    params: t.Dict[str, t.Any] = {},
    client: RestClient = InfoBloxClient,
) -> t.Iterable[t.List[t.Dict[str, JSON_Values]]]:
    """ Simple HTTP request that handles Infobox's pagination for us! """
    # Initial request
    response = client.request(
        url,
        query={
            **params,
            "_paging": 1,
            "_return_as_object": 1,
            # Infoblox breaks when there's more than 100
            "_max_results": 100,
        },
    ).json()

    yield response.get("result")

    next_page = response.get("next_page_id")

    while next_page:
        res_json = client.request(url, query={"_page_id": next_page}).json()
        yield res_json["result"]
        # We use get here so we don't worry about silly KeyExceptions
        next_page = res_json.get("next_page_id")


def add_network_ignore_voip(
    results: t.List[NETWORKBASE],
    json_res: t.List[NETWORKBASE],
) -> None:
    """ Adds networks we care about to some json_res!"""

    def filter_good_res(network: NETWORKBASE) -> bool:
        """We only care about networks that aren't VoIP"""
        view = network.get("network_view")
        if view and "voip" not in view.lower():
            post_network(t.cast(NETWORK, network))
            return True
        return False

    json_res.extend(filter(filter_good_res, results))


def get_all_networks() -> None:
    """
    Get all of the network ranges we're interested in
    By get, I mostly mean save to a file in `data/networks.json`
    """
    json_res: t.List[NETWORKBASE] = []
    print("Searching all available networks")
    # url/network?network=100.65.0.0/23&_return_as_object=1&_paging=1&_max_results=1&_return_fields+=...
    for page in InfoBoxPagination(
        "network",
        {
            "_return_fields+": ["network", "extattrs", "network_view"],
            "network_view": "DT-internal",
        },
    ):
        add_network_ignore_voip(t.cast(t.List[NETWORKBASE], page), json_res)

    fname = "data/networks_meta.json"
    with open(fname, "w") as f:
        f.write(str(json_res))

    print("\tAll done! Check the results in:")
    print(f"\t{fname}")


def iterate_through_network(callable: t.Callable[[NETWORKBASE], None]) -> None:
    print("Iterating through all networks in `data/networks.json`")
    with open("data/networks.json") as f:
        networks = json.load(f)
        for network in networks:
            callable(network)


def get_all_IPs() -> None:
    def print_subnet_to_json(network: NETWORKBASE) -> None:
        print("\tChecking out:", network["network"])
        json_res: t.List[IPV4ADDRESS] = []

        for res in InfoBoxPagination(
            "ipv4address",
            {
                "network": network["network"],
                "network_view": network["network_view"],
                # We don't care about IPs that aren't used
                "status": "USED",
                # Discovered DATA includes such info
                "_return_fields+": "discovered_data",
            },
        ):
            json_res.extend(t.cast(t.List[IPV4ADDRESS], res))

        # Save data to some file
        file_name = f"data/ips/{network['network'].replace('/', '_to_')}.json"
        with open(file_name, "w") as f:
            json.dump(json_res, f, ensure_ascii=False, indent=2)
            print("\t\tWritten results in: ", file_name)

    iterate_through_network(print_subnet_to_json)


def get_all_devices() -> None:
    def print_device_to_json(network: NETWORKBASE) -> None:
        print("Checking out:", network["network"])
        json_res: t.List[IPV4ADDRESS] = []
        for res in InfoBoxPagination(
            "ipv4address",
            {
                "network": network["network"],
                "network_view": network["network_view"],
                # We want _any_ipv4address that contains a mac_address
                # This means that it's an actual physical machine
                "mac_address~": ".+",
                # We don't care about IPs that aren't used
                "status": "USED",
                # Discovered DATA includes such info
                "_return_fields+": ["discovered_data"],
            },
        ):
            if type(res) == list:
                json_res.extend(t.cast(t.List[IPV4ADDRESS], res))
            else:
                json_res.append(t.cast(IPV4ADDRESS, res))
        # Save data to some file
        file_name = (
            f"data/devices_{network['network'].replace('/', '_to_')}.json"
        )
        with open(file_name, "w") as f:
            json.dump(json_res, f, ensure_ascii=False, indent=2)
            print("Written results in: ", file_name)

    iterate_through_network(print_device_to_json)


"""-------------------- Device42 Methods --------------------"""


def post_network(json_data: NETWORK) -> t.Tuple[t.Optional[int], str]:
    vlan_id, err = get_VLAN_id(json_data)
    network, mask = json_data["network"].split("/")
    new_subnet = {
        "network": network,
        "mask": mask,
        "vlan_id": vlan_id,
        "name": json_data.get("comment"),
        "notes": err,
    }
    return None, "TODO: figure out assigned and allocated"


def check_repeat_number_vlan(
    old_vlans: t.List[VlanD42], new_vlan: VlanD42
) -> t.Optional[VlanD42]:
    """VLANS are supposed to have the same number
    But sometimes, due to human error these things end up having the same
    number. Whoopsie

    This function verifies if we need to construct a new VLAN entry in
    Device42.
    """
    for old_vlan in old_vlans:
        if (
            old_vlan["name"] == new_vlan["name"]
            and old_vlan["description"] == new_vlan["description"]
        ):
            # Nothing todo
            return old_vlan
    # Whoopsie...
    # This means that the new_vlan wasn't the same as _any of the existing
    # vlans in the attributes we care about.
    # This means that we have to create a new VLAN
    return None


def get_VLAN_id(
    subnet: NETWORK, client: RestClient = D42Client
) -> t.Tuple[t.Optional[int], str]:
    """Get the VLAN ID for a given NETWORK.

    Returns:  (int | None, ErrString)

    The  ErrString is useful for when we receive bad data from the network
    itself (value is a range, or a string, etc)

    If the VLAN doesn't exist on the client, then we make a post asking politely
    for one to be added.

    This function _can_ be recursive, becasue some times the value of a VLAN
    is a range! This is dreadfully hairy, but if this happens we just return
    the first non-null value.

    If you're wondering why there's so many casts and mypy-ignore.
    Well...
    See: https://github.com/python/mypy/issues/4359
    AND: https://github.com/python/mypy/issues/4122#issuecomment-336924377
    """
    if (
        subnet.get("extattrs") is None
        or subnet["extattrs"].get("VLAN") is None
    ):
        # Nothing todo...
        return None, ""

    vlan: ExtraInfo = subnet["extattrs"]["VLAN"]

    try:
        split_value = list(map(int, vlan["value"].split("-")))
        assert len(split_value) in (1, 2)
    except (ValueError, AssertionError):
        return None, f'Warning 🚨: Could not decypher the VLAN: {vlan["value"]}'

    if len(split_value) == 2:
        """...shit
        The infoblox data isn't exactly the finest
        Some of the VLAN values are actually a hyphen separated range.
        Recursion time then!
        """
        multiple_results: t.List[t.Optional[int]] = []
        for new_number in range(split_value[0], split_value[1] + 1):
            mini_subnet: NETWORK = {
                **subnet,  # type: ignore
                "extattrs": {"VLAN": {"value": str(new_number)}},
            }
            multiple_results.append(
                get_VLAN_id(
                    mini_subnet,
                    client,
                )[0]
            )
        return (
            next(id for id in multiple_results if id is not None),
            f'Warning 🚨: found multiple VLANS: {vlan["value"]}',
        )

    json_data: VlanD42 = {
        "number": vlan["value"],
        # Max len of name is 64...
        "name": subnet.get("comment", "")[:64],
        "description": f"Vlan for subnetwork {subnet['network']}",
        "notes": (
            "Warning This entry was automatically generated by a "
            "script that queries Infoblox! Use with caution"
        ),
    }

    # We start off by getting any existing VLAN with the same number.
    previous_vlans = (
        client.request("vlans", query={"number": vlan["value"]})
        .json()
        .get("vlans", [])
    )

    old_vlan = check_repeat_number_vlan(previous_vlans, json_data)

    if old_vlan is not None:
        return int(old_vlan["vlan_id"]), ""

    # Ok, we _have_ to create a whole new VLAN
    if len(previous_vlans) > 1:
        json_data["notes"] = (
            "Warning 🚨: Two VLANS have the same number! "
            "This is likely a mistake\n"
            f"{json_data['notes']}"
        )

    """
    # D42 is particularly annoying with the bloody posts...
    # todo: REFACTOR RestClient
    client.request(
        "vlans/",
        data=json_data,  # type: ignore
        method="POST",
    )
    """
    res: Response = client.session().request(
        method="POST",
        url=f"{D42_Host}vlans/",
        data=json_data,
    )
    if res.status_code == 200:
        # See this:
        # https://api.device42.com/#!/IPAM/getIPAMvlans
        return int(res.json()["msg"][1]), ""
    raise RequestException(res.json()["msg"])


def post_all_VLANs() -> None:
    # We're safe to cast post_vlan since we check apply the necessary checks
    # and balances inside the function itself
    iterate_through_network(
        t.cast(t.Callable[[NETWORKBASE], None], get_VLAN_id)
    )


if __name__ == "__main__":
    # get_all_networks()
    # get_all_IPs()
    # get_all_devices()
    post_all_VLANs()
