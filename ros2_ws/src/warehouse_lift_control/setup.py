from setuptools import find_packages, setup


package_name = "warehouse_lift_control"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Ericasam2",
    maintainer_email="Ericasam2@users.noreply.github.com",
    description="Command and monitor the Unity warehouse robot lift.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "lift_command_node = warehouse_lift_control.lift_command_node:main",
        ],
    },
)
