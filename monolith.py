import requests
from bs4 import BeautifulSoup
import re
import datetime
import argparse

BASE_URL = "https://hub.docker.com/r/{user}/{image}/"
DOCKERFILE_URL = BASE_URL + "~/dockerfile/"

def get_dockerfile(name):
    """
       Given a name of the form
       
       user/image:tag
       user/image
       image
       image:tag
       
       Attempt to get the dockerfile and return the text
    """
    print('getting:' + name)
    regex = r"\A(?:([\w\-\d\.]+)\/)?([\w\-\d\.]+)(?::([\w\-\d\.]+))?\Z"
    user, image, tag = re.match(regex, name).groups()
    if user is None:
        user = '_'
    if tag is None:
        tag = ':latest'
    result = requests.get(DOCKERFILE_URL.format(user=user, image=image))
    # Make sure we got a page
    if 'RouteNotFound404Page' in result.content.decode():
        print('Unable to get dockerfile from {}'.format(name))
        return ''
    soup = BeautifulSoup(result.content, "html.parser")
    html = soup.select('span[class*="Dockerfile"]')[0]
    return html.text if html.text else ''

def get_from(dockerfile):
    """
       Given the text of a dockerfile, see where it was derived from
    """
    regex = r'^(?:(?!#).)*(?:FROM|from)\s+(\S+)'
    return re.search(regex, dockerfile, re.MULTILINE).groups()[0]

def get_tree(name):
    dockerfile = get_dockerfile(name)
    # TODO get hash
    s = "### {} --- {}\n".format(name, str(datetime.datetime.now()))
    s += dockerfile
    if dockerfile:
        name = get_from(dockerfile)
        return get_tree(name) + s
    return s

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Make a monolithic Dockerfile")
    parser.add_argument('-f', '--file', type=str, help="Where to write the file out to", default='Monolith.txt')
    parser.add_argument('image_name', type=str, help="The name of the image, as such: 'jupyterhub/jupyterhub'")
    args = parser.parse_args()

    monolith = get_tree(args.image_name)
    with open(args.file, 'w') as f:
        f.write(monolith)

