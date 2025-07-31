"""Setup script for the Israeli Government Decisions Scraper package."""

from setuptools import setup, find_packages
import os

# Read the requirements file
def read_requirements():
    """Read requirements from requirements.txt file."""
    req_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    if os.path.exists(req_file):
        with open(req_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

# Read the README for long description
def read_readme():
    """Read README for long description."""
    readme_file = os.path.join(os.path.dirname(__file__), 'docs', 'README.md')
    if os.path.exists(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    return "Israeli Government Decisions Scraper with Database Integration"

setup(
    name="gov2db",
    version="1.0.0",
    author="Gov2DB Project",
    description="Israeli Government Decisions Scraper with Database Integration",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/gov2db",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
        ]
    },
    entry_points={
        "console_scripts": [
            "gov2db-sync=gov_scraper.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
        "Topic :: Text Processing :: General",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="israeli government decisions scraper database supabase selenium",
    project_urls={
        "Documentation": "https://github.com/yourusername/gov2db/docs",
        "Source": "https://github.com/yourusername/gov2db",
        "Tracker": "https://github.com/yourusername/gov2db/issues",
    },
)