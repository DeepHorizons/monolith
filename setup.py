import setuptools

setuptools.setup(
    name="monolith",
    version="0.1",
    packages=['monolith'],
    scripts=['scripts/monolith'],
    install_requires=['requests>=2.18', 'beautifulsoup4>=4.6.0'],
)
