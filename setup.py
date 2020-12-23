from setuptools import setup, find_packages

setup(
    name="howsignbot-lib",
    version="1.0.0",
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
