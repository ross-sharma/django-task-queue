import pathlib
from setuptools import setup, find_packages

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="django-task-queue",
    version="2.0.1",
    description="Simple task queue for Python Django framework",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/ross-sharma/django-task-queue",
    author="Ross Sharma",
    author_email="ross@ross-sharma.com",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
    ],
    packages=find_packages(exclude=["dummy_project"]),
    include_package_data=True,
    install_requires=["django"],
    entry_points={
        "console_scripts": []
    },
)
