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
    install_requires=["pyyaml~=5.0"],
    extras_require=EXTRAS_REQUIRE,
    python_requires=">=3.8",
    packages=find_packages("lib"),
    package_dir={"": "lib"},
    package_data={
        "handshapes": ["assets/*.png"],
        "catchphrase": ["*.yaml"],
        "cuteid": ["*.json"],
    },
    include_package_data=True,
)
