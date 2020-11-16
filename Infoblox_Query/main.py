import requests
from requests import Response
from configparser import ConfigParser
from netaddr import IPNetwork
import urllib3
import json

import typing as t

JSON_Values = t.Union[str, int, float, bool, None]

urllib3.disable_warnings()

config = ConfigParser()
config.read(filenames="infoblox_setup.cfg")

Info_User = config["infoblox"]["USER"]
Info_Pass = config["infoblox"]["PASS"]
Info_Host = config["infoblox"]["HOST"]

Info_URL = f"https://{Info_Host}/wapi/v2.2/"


def InfoGet(query: t.Dict[str, t.Any], url: str) -> Response:
    return requests.request(
        "GET",
        f"{Info_URL}{url}",
        auth=(Info_User, Info_Pass),
        params=query,
        verify=False,
    )


def HandleInfoBoxPagination(
    url: str,
    initial_next_page: str,
    callable: t.Callable[..., None] = lambda x: print(x),
) -> None:
    next_page = initial_next_page
    while next_page:
        res = InfoGet({"_page_id": next_page}, url).json()
        callable(res["result"])
        next_page = res.get("next_page_id")


def InfoBoxPagination(
    url: str, params: t.Dict[str, t.Any]
) -> t.Iterable[t.Iterable[JSON_Values]]:
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
    ).json()

    print(response["result"])
    yield response["result"]

    next_page = response.get("next_page_id")

    while next_page:
        res = InfoGet({"_page_id": next_page}, url)
        print("Just made a request to:", res.url)
        res_json = res.json()
        print(res_json["result"])
        yield res_json["result"]
        next_page = res_json.get("next_page_id")


def get_all_networks() -> None:
    session = requests.Session()
    session.auth = (Info_User, Info_Pass)
    session.verify = False
    json_res = []

    response = InfoGet(
        {
            "_return_fields": ["network", "extattrs"],
            "_max_results": 99,
            "_paging": 1,
            "_return_as_object": 1,
        },
        "network",
    ).json()

    json_res.extend(response["result"])

    HandleInfoBoxPagination(
        "network",
        response["next_page_id"],
        lambda results: json_res.extend(results),
    )

    with open("data/networks.json", "w") as f:
        f.write(str(json_res))

    print("All done!")


def iterate_through_network(
    network: str,
) -> t.Iterator[t.Any]:
    IPs: t.Iterable[str] = IPNetwork(network).iter_hosts()
    for IP in IPs:
        res = InfoGet({"network": IP}, "ipv4address")
        print("Just sent a GET to", res.url)
        yield res.json()


def yo() -> None:
    with open("data/networks.json") as f:
        json_res: t.List[t.Any] = []
        networks = json.load(f)
        for network in networks:
            for res in InfoBoxPagination(
                "ipv4address",
                {"network": network["network"]},
            ):
                if type(res) == list:
                    json_res.extend(res)
                else:
                    json_res.append(res)
            with open("data/ips.json", "w") as f:
                f.write(str(json_res))
            return


if __name__ == "__main__":
    yo()
