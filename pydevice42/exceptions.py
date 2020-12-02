class Device42Exception(Exception):
    pass


class ReturnCodeException(Device42Exception):
    pass


class Device42LicenseException(Device42Exception):
    pass


class LicenseExpiredException(Device42LicenseException):
    pass


class LicenseInsufficientException(Device42LicenseException):
    pass
