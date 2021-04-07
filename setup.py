from setuptools import find_packages, setup

setup(
    name="pysen_ls",
    version="0.1.0",
    packages=find_packages(),
    description="A language server implementation for pysen",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Yuki Igarashi",
    author_email="me@bonprosoft.com",
    url="https://github.com/bonprosoft/pysen-ls",
    license="MIT License",
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Operating System :: MacOS",
        "Operating System :: Unix",
    ],
    install_requires=[
        "dataclasses>=0.6,<1.0;python_version<'3.7'",
        "pygls>=0.10.0,<0.11.0",
        "pysen>=0.9.1,<0.10.0",
    ],
    package_data={"pysen_ls": ["py.typed"]},
    entry_points={"console_scripts": ["pysen_language_server=pysen_ls.__main__:main"]},
)
