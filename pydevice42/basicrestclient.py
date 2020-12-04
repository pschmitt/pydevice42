import functools
import typing as t

import requests
import urllib3

from . import types as tt
from .logger import LOGGER


class BasicRestClient:
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
        self.session: requests.Session = self.prepareSession()

    def prepareSession(self) -> requests.Session:
        s = requests.Session()
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
        method: tt.HTTP_METHODS = "GET",
    ) -> requests.Response:
        request = functools.partial(
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
