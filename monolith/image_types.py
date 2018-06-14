import logging
import re
from bs4 import BeautifulSoup
import requests

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

    @classmethod
    def get_dockerfile(cls, name):
        """
           Given a name of the form

           user/image:tag
           user/image
           image
           image:tag

           Attempt to get the dockerfile and return the text
        """
        logging.debug('getting: ' + name)
        info = cls.get_docker_info(name)
        logging.debug('User: {user}; Image: {image}; Tag: {tag}'.format(user=info.user, image=info.image, tag=info.tag))

        # TODO figure out tag as well
        # Make a call out to get the page
        logging.debug("Getting from dockerhub")
        result = requests.get(DOCKERFILE_URL.format(user=info.user, image=info.image))
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

    @staticmethod
    def get_docker_info(name):
        """
        Given a name of the form
       
        user/image:tag
        user/image
        image
        image:tag
        image@sha256:digest
        user/image@sha256:digest

        make an object that represents it
        """
        # Get everything in the form given in the docstring. Include characters, digits, and '-'
        # Note that the ref needs the `sha256:` bit, so it also needs the `:` in the capture group
        regex = r"^(?:([\w\-\d\.]+)\/)?([\w\-\d\.]+)(?:[:|\@]([@:\w\-\d\.]+))?$"

        # Get the values, set default ones if need be
        user, image, tag = re.match(regex, name).groups()
        if user is None:
            # TODO XXX This may be `library` OR `_` depending on some external stuff
            #user = 'library'
            user = '_'
        if tag is None:
            tag = 'latest'
        
        class _DockerInfo:
            def __init__(self, user, image, tag):
                self.user = user
                self.image = image
                self.ref = tag  # TODO remove this
                self.tag = tag
        
        return _DockerInfo(user=user, image=image, tag=tag)

    def gen_name(self):
        """
        Generate the string that docker expects as the "name",
        or "user/image"
        """
        info = self.get_docker_info(self.name)
        return "{user}/{image}".format(user=info.user, image=info.image)

