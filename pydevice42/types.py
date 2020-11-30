from typing import Dict, List, Literal, Optional, TypedDict, TypeVar, Union

# Representing JSON is notoriously tricky in mypy
# Here's the best attempt I have so far
# A JSON_RES is either a list of JSON_DICTS, or just a straight up JSON_DICT
# JSON_LIST contains JSON_DICTS
# And a JSON_DICT is a simple map to acceptable JSON_VALUES
# So JSONS that contain JSONS are not acceptable, because MYPY can't represent
# self-referential values
# Meaning that if we get some sort of fancy value, we have to cast it
# to the appropriately typed dict
JSON_Values = Union[str, int, float, bool, None]

JSON_Dict = Dict[str, JSON_Values]

JSON_List = List[JSON_Dict]

JSON_Res = Union[JSON_List, JSON_Dict]

HTTP_METHODS = Literal["GET", "POST", "PUT"]
STATUS = Literal["USED", "UNUSED"]
T = TypeVar("T")


class Vlan(TypedDict, total=False):
    number: str
    name: str
    description: str
    notes: str
    vlan_id: str


class SubnetBase(TypedDict):
    network: str
    mask_bits: str
    name: str


class Subnet(SubnetBase, total=False):
    description: str
    notes: str


class StorageServiceInstance(TypedDict):
    service_name: Literal["storage_service"]
    # id that points over to a Clustered Device that houses our LUNS!
    device_id: int


class CustomFieldBase(TypedDict):
    """
    Editing a custom field should be as simple as sending these to
    the relevant API.

    Getting them is a little trickier, for now I created a DOQL Query.
    """

    # ID of whichever other object you're editing
    id: int
    key: str
    value: str


class ServiceInstanceCustomField(CustomFieldBase, total=False):
    """POST/PUT: /api/1.0/custom_fields/serviceinstance

    GET: /data/v1.0/query/?saved_query_name
    =get_service_instance_custom_fields
    &delimiter=,&header=yes&output_type=json
    """

    serviceinstance_fk: int
    service_name: str
    type_id: int
    type: str
    related_model_name: Optional[int]
    filterable: bool
    mandatory: bool
    log_for_api: bool
    is_multi: bool
    notes: str
