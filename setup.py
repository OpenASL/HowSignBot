from setuptools import setup, find_packages

EXTRAS_REQUIRE = {
    "dev": ["flake8==3.8.3", "flake8-bugbear==20.1.4", "pre-commit~=2.3"],
}


def read(fname):
    with open(fname) as fp:
        content = fp.read()
    return content


setup(
    name="howsignbot-lib",
    version="1.0.0",
    # TODO: Move these all to requirements.txt?
    install_requires=[
        # catchphrase
        "pyyaml>=5.0",
        # meetings
        "python-slugify>=4.0",
        # cuteid
        "emoji>=0.6.0",
        # database
        "databases[postgresql]==0.4.0",
        "SQLAlchemy==1.3.19",
        "alembic==1.4.3",
        "pytz",
    ],
    extras_require=EXTRAS_REQUIRE,
    python_requires=">=3.8",
    packages=find_packages("lib"),
    package_dir={"": "lib"},
    package_data={
        "catchphrase": ["*.yaml", "*.json"],
        "clthat": ["*.json"],
        "cuteid": ["*.json"],
        "handshapes": ["assets/*.png"],
    },
    include_package_data=True,
)
