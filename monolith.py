#! /usr/bin/env python
"""
Make a monolithic dockerfile from a given image name
"""
import requests
from bs4 import BeautifulSoup
import re
import datetime
import argparse
import logging

logging.basicConfig(level=logging.DEBUG)

BASE_URL = "https://hub.docker.com/r/{user}/{image}/"
DOCKERFILE_URL = BASE_URL + "~/dockerfile/"

class DockerImage:
    def __init__(self, name, dockerfile = None, children = None, parent = None):
        self.name = name
        self.dockerfile = dockerfile if dockerfile else ""
        self.children = children if children else {}
        self.parent = parent if parent else None

    def is_root(self):
        return True if self.parent else False

    def get_lineage(self):
        """
        Return a list of the images between the root and this image
        """
        if self.parent:
            return [*self.parent.get_lineage(), self]
        else:
            return [self]

    @staticmethod
    def get_dockerfile(name):
        """
           Given a name of the form

           user/image:tag
           user/image
           image
           image:tag

           Attempt to get the dockerfile and return the text
        """
        logging.debug('getting: ' + name)
        # Get everything in the form given in the docstring. Include characters, digits, and '-'
        regex = r"^(?:([\w\-\d\.]+)\/)?([\w\-\d\.]+)(?::([@:\w\-\d\.]+))?$"

        # Get the values, set default ones if need be
        user, image, tag = re.match(regex, name).groups()
        if user is None:
            user = '_'
        if tag is None:
            tag = ':latest'
        logging.debug('User: {user}; Image: {image}; Tag: {tag}'.format(user=user, image=image, tag=tag))

        # Make a call out to get the page
        logging.debug("Getting from dockerhub")
        result = requests.get(DOCKERFILE_URL.format(user=user, image=image))
        logging.debug("request complete")
        # Make sure we got a page, dockerhub does not return a 404 if the page does not exist
        if 'RouteNotFound404Page' in result.content.decode():
            logging.error('Unable to get dockerfile from {}'.format(name))
            return ''

        # Parse it, get the span that has the dockerfile text
        logging.debug("Parsing html")
        soup = BeautifulSoup(result.content, "html.parser")
        block = soup.select('div[class*="hljs"]')
        if not block:
            logging.warning("No block")
            return ''
        if len(block) > 1:
            logging.warning("Multiple blocks found; Using first")

        text = block[0].text  # .text removes any html tags
        logging.debug("complete: ---")
        logging.debug(text)
        logging.debug("---")
        # Return the text
        return text or ''

    @staticmethod
    def get_from(dockerfile):
        """
           Given the text of a dockerfile, see where it was derived from
        """
        # Look for the string `FROM` that is not prefaced with a comment
        regex = r'^(?:(?!#).)*(?:FROM|from)\s+(\S+)'
        return re.search(regex, dockerfile, re.MULTILINE).groups()[0]

    @classmethod
    def get_tree(cls, name):
        curr_img = cls(name=name)
        dockerfile = cls.get_dockerfile(name)
        curr_img.dockerfile = dockerfile
        while dockerfile:
            name = cls.get_from(dockerfile)  # Get the next image name
            new_img = cls(name=name)

            # Update references
            curr_img.parent = new_img
            new_img.children[curr_img.name] = curr_img
            curr_img = new_img

            # Get next iteration
            dockerfile = cls.get_dockerfile(name)
            curr_img.dockerfile = dockerfile
        return curr_img


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Make a monolithic Dockerfile")
    parser.add_argument('-f', '--file', type=str, help="Where to write the file out to", default='Monolith.txt')
    parser.add_argument('image_name', type=str, help="The name of the image, as such: 'jupyterhub/jupyterhub'")
    args = parser.parse_args()

    root = DockerImage.get_tree(args.image_name)

    def get_single_dockerfiles(image):
        """
        Return a string that is the concatenation of all the dockerfiles related to `image`
        """
        if len(image.children) > 1 :
            # TODO add functionality
            raise Exception("No way to handle diverging trees yet")
            child = image.children.items
        return "### {name} --- {date}\n{current_dockerfile}\n{next}".format(name=image.name, date=str(datetime.datetime.now()),
                                                                     current_dockerfile=image.dockerfile, next=get_single_dockerfiles(list(image.children.values())[0]) if image.children else '')
    monolith = get_single_dockerfiles(root)
    with open(args.file, 'w') as f:
        f.write(monolith)

