import typing as t
from functools import partial

import urllib3
from requests import RequestException, Response, Session

from .types import (
    HTTP_METHODS,
    CustomFieldBase,
    ServiceInstanceCustomField,
    Subnet,
)


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
        # Disable certificate warnings
        urllib3.disable_warnings()
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
        params: t.Optional[t.Dict[str, t.Any]] = None,
        json: t.Optional[t.Dict[str, t.Any]] = None,
        data: t.Optional[t.Dict[str, t.Any]] = None,
        method: HTTP_METHODS = "GET",
    ) -> Response:
        request = partial(
            self.session().request,
            method,
            f"{self._host}{url}",
            params=params,
            json=json,
            data=data,
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


class D42Client(RestClient):
    def _check_err(self, res: Response) -> t.Tuple[int, str]:
        """Collect the error like so:

        ```python
        >>> e = RequestException(res)
        >>> type(e.args[0]) == Response
        True
        ```

        You can also get the request by doing:

        ```python
        >>> # This is useful to debug the body of a function or to use curlify
        >>> RequestException(res).args[0].request
        >>> curlify.to_curl(RequestException(res).args[0].request)
        "curl -X GET -H 'Accept: */*' -H '..."
        ```

        """
        js = res.json()
        if res.status_code == 200:
            # See this as an example:
            # https://api.device42.com/#!/IPAM/postIPAMsubnets
            return int(js["code"]), " ".join(map(str, js.get("msg", [])))
        raise RequestException(res)

    def post_network(self, new_subnet: Subnet) -> t.Tuple[int, str]:
        return self._check_err(
            self.request(
                url="/api/1.0/subnets/",
                method="POST",
                data=t.cast(t.Dict[str, t.Any], new_subnet),
            )
        )

    def _get_DOQL_query(self, query_name: str) -> t.Any:
        """
        DOQL queries are custom usermade queries that talk directly to
        the database and (generally) return a JSON.

        They have to be coded by the user.
        """
        res = self.request(
            method="GET",
            url="/services/data/v1.0/query/",
            params={
                "saved_query_name": query_name,
                "delimiter": "",
                "header": "yes",
                "output_type": "json",
            },
        )
        if res.status_code != 200:
            raise RequestException(res)
        return res.json()

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
    ) -> t.Tuple[int, str]:
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
        return self._check_err(
            self.request(
                method="PUT",
                url="/api/1.0/custom_fields/serviceinstance/",
                data=t.cast(t.Dict[str, t.Any], cf),
            )
        )
