import json as js
import logging
import typing as t
from functools import partial

import urllib3
from requests import HTTPError, Response, Session

from .types import (
    HTTP_METHODS,
    CustomFieldBase,
    JSON_Res,
    ServiceInstanceCustomField,
    Subnet,
)

LOGGER = logging.getLogger(__name__)


class Device42Exception(Exception):
    pass


class ReturnCodeException(Device42Exception):
    pass


class LicenseExpiredException(Device42Exception):
    pass


class RestClient:
    """The requests library handles mantaining a session alive and cookies for
    us.

    This class is a simple namespace to get that sorted out for us
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        insecure: bool = False,
        port: int = 443,
    ) -> None:
        self._username = username
        self._password = password
        self._hostname = hostname
        self._insecure = insecure
        self._port = port
        self.session: Session = self.prepareSession()

    def prepareSession(self) -> Session:
        s = Session()
        s.auth = (self._username, self._password)
        if self._insecure:
            # Disable certificate warnings
            urllib3.disable_warnings()
            s.verify = False
        self._session = s
        return self._session

    def request(
        self,
        url: str,
        params: t.Optional[t.Dict[str, t.Any]] = None,
        json: t.Optional[t.Dict[str, t.Any]] = None,
        data: t.Optional[t.Dict[str, t.Any]] = None,
        method: HTTP_METHODS = "GET",
    ) -> Response:
        request = partial(
            self.session.request,
            method,
            f"https://{self._hostname}:{self._port}{url}",
            params=params,
            json=json,
            data=data,
            verify=not self._insecure,
        )
        try:
            res = request()
            LOGGER.debug(f"Request response: {res.text}")
            return res
        except ConnectionResetError:
            """
            If we're making too many requests the server might reset the
            connection. If so we try again but don't catch any further
            Exceptions, if they appear that means we have problems
            """
            self.prepareSession()
            return request()


class D42Client(RestClient):
    def _check_err(self, jres: t.Any) -> JSON_Res:
        """POST and PUT method validation

        Raises exception if the return code isn't 0.

        Else, returns the message from the server.
        This is _generally_ a t.List[t.Any], but I have generalised it to
        be any type of JSON_Res
        """
        ret_code = int(jres["code"])
        ret_msg = t.cast(t.List[t.Any], jres.get("msg", []))
        if ret_code != 0:
            raise ReturnCodeException(" ".join(map(str, ret_msg)))
        return t.cast(JSON_Res, ret_msg)

    def _request(
        self,
        endpoint: str,
        params: t.Optional[t.Dict[str, t.Any]] = None,
        json: t.Optional[t.Dict[str, t.Any]] = None,
        data: t.Optional[t.Dict[str, t.Any]] = None,
        method: HTTP_METHODS = "GET",
    ) -> JSON_Res:
        res = self.request(
            url=endpoint, params=params, json=json, data=data, method=method
        )
        try:
            res.raise_for_status()
        except HTTPError as err:
            if err.response.status_code == 500:
                try:
                    msg = err.response.json().get("msg", "")
                    if msg.startswith("License expired"):
                        raise LicenseExpiredException(msg) from err
                except js.JSONDecodeError:
                    # Ignore JSON decode exception here. The backend may not
                    # talk JSON when returning 500's.
                    pass
            raise
        jres: JSON_Res = res.json()
        if method in ["POST", "PUT"]:
            return self._check_err(jres)
        return jres

    def post_network(self, new_subnet: Subnet) -> JSON_Res:
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
    ) -> t.List[ServiceInstanceCustomField]:
        """
        Requires that you've setup a DOQL custom query

        Yes it sucks, but I honestly haven't found a better way :(
        """
        return t.cast(
            t.List[ServiceInstanceCustomField],
            self._get_DOQL_query("get_service_instance_custom_fields"),
        )

    def update_custom_field_service_instance(
        self, cf: CustomFieldBase
    ) -> JSON_Res:
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

    def get_all_devices(self) -> JSON_Res:
        return self._request(
            method="GET",
            endpoint="/api/1.0/devices/all/",
        )
