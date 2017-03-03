# Monolith
Monolith is a python file for creating monolithic Dockerfiles that can be used for verification of an image.


## Installation
The two requirements of to run the script are `requests` and `BeautifulSoup`.

```
pip install requests beautifulsoup4
```
or
```
pip install -r requirements.txt
```


## Usage
Simply pass in the image name in the form "user/image".
The script will write it out to a file named `Monolith.txt` by default.
To change that, set the `-f` or `--file` parameter.

```
monolith.py jupyterhub/jupyterhub
```

## Notes
* This does not grab the exact dockerfile that was used, just the one that is available on dockerhub.
* Tags are currently ignored.

