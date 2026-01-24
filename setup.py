#!/usr/bin/env python3
"""Setup script for jeeves-airframe package."""

from setuptools import setup, find_packages

setup(
    name="jeeves-airframe",
    version="0.1.0",
    description="Inference platform abstraction layer for Jeeves",
    author="Jeeves Cluster Organization",
    author_email="engineering@jeeves-cluster.local",
    url="https://github.com/Jeeves-Cluster-Organization/jeeves-airframe",
    license="Apache License 2.0",
    packages=find_packages(include=["airframe*"]),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.25.0,<1.0.0",
        "pydantic>=2.0.0,<3.0.0",
        "structlog>=23.0.0",
    ],
    extras_require={
        "k8s": [
            "kubernetes>=28.0.0,<29.0.0",
            "PyYAML>=6.0",
        ],
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
            "mypy>=1.0.0",
        ],
    },
    include_package_data=True,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
