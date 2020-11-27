from setuptools import find_packages, setup

setup(
    name="pydevice42",
    packages=find_packages(),
    package_data={"pydevice42": ["py.typed"]},
)
