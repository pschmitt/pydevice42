import json as js
import typing as t

import requests

from . import exceptions as d42exc
from . import types as tt
from .basicrestclient import BasicRestClient
from .logger import LOGGER


def extract_data(data: t.Dict) -> t.Any:
    metadata_keys = ["offset", "total_count", "limit"]
    return data.get([k for k in list(data.keys()) if k not in metadata_keys][0])


def flatten(t: t.List) -> t.List:
    flat_list = []
    for sublist in t:
        for item in sublist:
            flat_list.append(item)
    return flat_list


class D42Client(BasicRestClient):
    def _check_err(self, jres: t.Any) -> tt.JSON_Res:
        """POST and PUT method validation

        Raises exception if the return code isn't 0.

        Else, returns the message from the server.
        This is _generally_ a t.List[t.Any], but I have generalised it to
        be any type of tt.JSON_Res
        """
        ret_code = int(jres["code"])
        ret_msg = jres.get("msg", [])
        if ret_code != 0:
            raise d42exc.ReturnCodeException(" ".join(map(str, ret_msg)))
        return ret_msg

    def _request(
        self,
        endpoint: str,
        params: t.Optional[t.Dict[str, t.Any]] = None,
        json: t.Optional[t.Dict[str, t.Any]] = None,
        data: t.Optional[t.Dict[str, t.Any]] = None,
        method: tt.HTTP_METHODS = "GET",
    ) -> tt.JSON_Res:
        res = self.request(
            url=endpoint, params=params, json=json, data=data, method=method
        )
        try:
            res.raise_for_status()
        except requests.HTTPError as err:
            if err.response.status_code == 500:
                try:
                    msg = err.response.json().get("msg", "")
                    if msg.startswith("License expired"):
                        raise d42exc.LicenseExpiredException(msg) from err
                    elif msg.startswith("License is not valid for"):
                        raise d42exc.LicenseInsufficientException(msg) from err
                except js.JSONDecodeError:
                    # Ignore JSON decode exception here. The backend may not
                    # talk JSON when returning 500's.
                    pass
            raise
        jres: tt.JSON_Res = res.json()
        if method in ["POST", "PUT"]:
            return self._check_err(jres)
        return jres

    def _paginated_request(
        self,
        endpoint: str,
        # FIXME Is there any paginated *non-* GET request?
        method: tt.HTTP_METHODS = "GET",
        params: t.Optional[t.Dict[str, t.Any]] = None,
        json: t.Optional[t.Dict[str, t.Any]] = None,
        data: t.Optional[t.Dict[str, t.Any]] = None,
        limit: int = 4,
    ) -> t.Iterable[tt.JSON_Res]:
        def page_request(new_params: t.Dict[str, t.Any]) -> tt.JSON_Dict:
            return t.cast(
                tt.JSON_Dict,
                self._request(
                    method=method,
                    endpoint=endpoint,
                    params=new_params,
                    data=data,
                    json=json,
                ),
            )

        request_num = 1
        params = {} if params is None else params
        params["limit"] = limit
        params["offset"] = 0

        # First request
        resp = page_request(params)

        # Process data
        total_count = tt.int_cast(resp.get("total_count"))
        resp_data: t.Any = extract_data(resp)
        yield resp_data

        processed = len(resp_data)

        while processed < total_count:
            params["offset"] += limit
            request_num += 1
            LOGGER.debug(
                f"Processing request #{request_num}) "
                f"[Offset: {params['offset']} - Limit: {limit}] "
                f"{len(resp_data)}/{total_count}"
            )
            resp = page_request(params)
            resp_data = extract_data(resp)
            processed += len(resp_data)
            yield resp_data

    def _flattened_paginated_request(
        self, *args: t.Any, **kwargs: t.Any
    ) -> t.Iterable[tt.JSON_Res]:
        return flatten(t.cast(t.List, self._paginated_request(*args, **kwargs)))

    def post_network(self, new_subnet: tt.SubnetBase) -> tt.JSON_Res:
        return self._request(
            endpoint="/api/1.0/subnets/",
            method="POST",
            data=t.cast(t.Dict[str, t.Any], new_subnet),
        )

    def _get_DOQL_query(self, query_name: str) -> t.Any:
        """
        DOQL queries are custom usermade queries that talk directly to
        the database and (generally) return a JSON.

        They have to be coded by the user.
        """
        return self._request(
            method="GET",
            endpoint="/services/data/v1.0/query/",
            params={
                "saved_query_name": query_name,
                "delimiter": "",
                "header": "yes",
                "output_type": "json",
            },
        )

    def get_custom_fields_of_service_instances(
        self, save_to_file: bool = False
    ) -> t.List[tt.ServiceInstanceCustomField]:
        """
        Requires that you've setup a DOQL custom query

        Yes it sucks, but I honestly haven't found a better way :(
        """
        return t.cast(
            t.List[tt.ServiceInstanceCustomField],
            self._get_DOQL_query("get_service_instance_custom_fields"),
        )

    def update_custom_field_service_instance(
        self, cf: tt.CustomFieldBase
    ) -> tt.JSON_Res:
        """Note that CustomFieldBase's `value` is a string!

        This means that if you're inputting a json as a custom field
        you should cast it with `json.dumps`

        Example:

        ```python
        >>> client = D42Client(user, password, host)
        >>> client.update_custom_field_service_instance(
        ...             {
        ...                 "id": 12,
        ...                 "key": "custom_data",
        ...                 "value": {
        ...                     "Testing": "I was sent from the API"
        ...                 },
        ...             }
        ...         )
        Traceback (most recent call last):
        ...
        requests.exceptions.RequestException: <Response [500]>
        >>> client.update_custom_field_service_instance(
        ...             {
        ...                 "id": 12,
        ...                 "key": "custom_data",
        ...                 "value": dumps({
        ...                     "Testing": "I was sent from the API"
        ...                 }),
        ...             }
        ...         )
        (0, 'custom key pair values added or updated ...')
        ```
        """
        return self._request(
            method="PUT",
            endpoint="/api/1.0/custom_fields/serviceinstance/",
            data=t.cast(t.Dict[str, t.Any], cf),
        )

    def get_all_devices(self) -> tt.JSON_Res:
        return self._request(
            method="GET",
            endpoint="/api/1.0/devices/all/",
        ).get("Devices")

    def get_all_service_instances(self) -> tt.JSON_Res:
        return self._flattened_paginated_request("/api/2.0/service_instances/")

    def get_all_application_components(self) -> tt.JSON_Res:
        return self._flattened_paginated_request("/api/2.0/appcomps/")

    def get_all_operating_systems(self) -> tt.JSON_Res:
        return self._flattened_paginated_request("/api/1.0/operatingsystems/")
