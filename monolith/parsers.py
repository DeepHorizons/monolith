import re
import inspect
import os
import subprocess
import shlex


class DockerFileToSingularityFile:
    # TODO get the proper runscript
    FILE_TEMPLATE = """
Bootstrap: {bootstrap}
From: {image}

%setup
    # Commands to be run on the host system after the os has been copied
    # Has access to $SINGULARITY_ROOTFS to access the root filesystem
    # Acts like ordinary shell
    {setup}


%files
    # Files to be copied to the container before %post
    # Docker ADD, COPY
    # Must be in the format:
    #
    # filename1
    # filename2 /home/placetogo/
    #
    # filename1 will be placed into the root of the filesystem
    {files}


%labels
    # Metadata to add to the image
    # Must be in the format
    #
    # <key> <value>
    # VERSION 5
    {labels}


%post
    # commands to be executed inside container during bootstrap
    # Has access to %files and %setup, and maybe %labels via /.singularity.d/labels.json
    # Has access to $SINGULARITY_ENVIRONMENT to be able to set build time generated environment variables available at run time
    # For example:
    #
    # echo 'export JAWA_SEZ=wutini' >> $SINGULARITY_ENVIRONMENT
    {post}


%environment
    # Environmental variables to be added AT RUN TIME
    # These variables are not available in %post
    # This must be in the form of:
    #
    # FOO=BAR
    # ABC=123
    # export FOO ABC
    #
    {environment}


%runscript
    # commands to be executed when the container runs
    if [ -z "$1" ]
    then
        exec {entrypoint} {cmd}
    else
        exec {entrypoint} "$@"
    fi


%test
    # Singularity can run tests, put that here
    # Acts like a normal shell
    {test}

"""
    # The first character doesn't get a slash, so we add it in the first one
    PARAM_ALLOWABLE_CHARACTERS_REGEX = '\w\ \t\\' + '\\'.join("!@#$%^&*()-_=+[{]}\|;:'\",<.>/?~`")
    PARAM_PATTERN = r'(?:[{PARAM_ALLOWABLE_CHARACTERS_REGEX}]+\s*\\\s*)*(?:[{PARAM_ALLOWABLE_CHARACTERS_REGEX}]+)\n'.format(PARAM_ALLOWABLE_CHARACTERS_REGEX=PARAM_ALLOWABLE_CHARACTERS_REGEX)
    SEARCH_PATTERN = r'^\s*(\w+)\s+({PARAM_PATTERN})'.format(PARAM_PATTERN=PARAM_PATTERN)

    def __init__(self, docker_image_name, folder='./'):
        self.clear_state()
        self.docker_image_name = docker_image_name  # Needed for pulling images from dockerhub
        self.folder = folder
        self.dockerfile_code = []
        
        self.ops = {}
        
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            # Instructions are defined by being all uppercase
            if name.isupper():
                self.ops[name] = method

    def clear_state(self):
        self.bootstrap = ""
        self.image = ""
        self._setup = ""  # TODO do I need this?
        self.setup = ""
        self.files = ""
        self.labels = ""
        self.post = ""
        #self.environment = ""
        self._environment = {}
        self.entrypoint = ""
        self.cmd = ""
        self.test = ""
        self.docker_workdir = "/"
    
    def parse(self, code):
        self.dockerfile_code.append(code)

        # Remove all comment lines
        code = '\n'.join([line for line in code.split('\n') if not re.match(r'^\s*#', line)])
        # Need an empty line at the end
        if not code.endswith('\n'):
            code += '\n'

        for inst, params in re.findall(self.SEARCH_PATTERN, code, re.MULTILINE):
            # Remove any extra lines in params
            # XXX Need to find a better way to do this
            params = '\n'.join([line for line in params.split('\n') if line.split()]) + '\n'
            print('inst: `{inst}`; params: `{params}`'.format(inst=inst, params=params.strip()))
            self.post += '\n    # {inst} {params}'.format(inst=inst, params=params.replace('\\', '').replace('\'', '').replace('"', '')[:min([30, params.find('\n')]) if len(params) > 30 else len(params)].strip() + '...' if len(params) > 30 else '')
            op = self.ops[inst]
            op(params)


    def singularity_file(self):
        """
        Return the formated Singularity file
        """
        return self.FILE_TEMPLATE.format(bootstrap=self.bootstrap,
                                         image=self.image,
                                         setup=self.setup,
                                         files=self.files,
                                         labels=self.labels,
                                         post=self.post,
                                         environment=self.environment,
                                         entrypoint=self.entrypoint,
                                         cmd=self.cmd,
                                         test=self.test)

    def write_singularity_file(self, filename='Singularity'):
        with open(os.path.join(self.folder, filename), 'w') as f:
            f.write(self.singularity_file())
    
    def dockerfile(self):
        return ''.join(self.dockerfile_code)
    
    def write_dockerfile(self, filename='Dockerfile'):
        with open(os.path.join(self.folder, filename), 'w') as f:
            f.write(self.dockerfile())
    @property
    def setup(self):
        """
        Why is `setup` done this way? Because it is imperative that any code
        that goes here is properly escaped or sanitized or whatever.
        This code runs on the host machine, don't let any untrusted code get here
        """
        return self._setup
    
    @setup.setter
    def setup(self, val):
        self._setup = val
    
    @property
    def environment(self):
        values = '\n    '.join(["{key}={value}".format(key=key, value=value) for key, value in self._environment.items()])
        if values:
            return values + '\n    export ' + ' '.join([key for key in self._environment])
        else:
            return '\n'
    
    def get_list_string(self, params):
        regex = r'\[(.+)\]'
        m = re.match(regex, params)
        if not m:
            raise Exception("Malformed params `{params}`".format(params=params))
        s, = m.groups()
        # TODO we may want to redo this instead as recursively looking for a pair of "
        s = s.split(',')
        return ' '.join(s)
    
    def get_key_value_pairs(self, params):
        # Linearize it
        params = ' '.join((line.replace('\\', '').strip() for line in params.splitlines()))
        no_double_quotes = self.PARAM_ALLOWABLE_CHARACTERS_REGEX.replace('\"', '')
        regex = r'([\w\.\d]+)[=\s+]((?:[{no_double_quotes}]+)|(?:\"[{no_double_quotes}]+\"))'.format(no_double_quotes=no_double_quotes)
        regex = self.SEARCH_PATTERN.replace('\"', '')
        regex = r'([\w\.\d]+)[=\s+]?((?:[{no_double_quotes}]+)|(?:\"[{no_double_quotes}]+\"))?'.format(no_double_quotes=no_double_quotes)
        pairs = []
        while params:
            # Get one match, then do it again on the rest of the string
            m = re.match(regex, params)
            if not m:
                raise Exception("Malformed params: {params}".format(params=params.encode()))
            key, value = m.groups()
            pairs.append((key, value))
            params = params[m.span()[1]:].strip()
        return pairs
        
    def ARG(self, params):
        """
        Set up the environment before FROM
        This is the only instruction allowed to run before FROM
        ARG VAR1=VAL1 \
            VAL2
        ARG <name>[=<default value>]
        """
        for key, value in self.get_key_value_pairs(params):
            self._environment[key] = value

    def FROM(self, params):
        """
        FROM <image> [AS <name>]
        FROM <image>[:<tag>] [AS <name>]
        FROM <image>[@<digest>] [AS <name>]
        """
        # First we need to substitute variables in environment with the params
        if self.image:
            self.post += '    # skipped, already have image'.format(params=params)
            return
        for key in self._environment:
            # ${variable} format
            search_list = ['${key}'.format(key=key), '${{{key}}}'.format(key=key)]
            for s in search_list:
                if s in params:
                    # Do replacement
                    params = params.replace(s, self._environment[key])
                    continue
            

        # Encountering a new FROM clears all state
        self.clear_state()
        self.post += '\n    # FROM {params}'.format(params=params.strip())

        print('---FROM: ' + params)
        # Get everything in the form given in the docstring. Include characters, digits, and '-'
        regex = r"^(?:([\w\-\d\.]+)\/)?([\w\-\d\.]+)(?::([@:\w\-\d\.]+))?$"

        # Get the values, set default ones if need be
        m = re.match(regex, params)
        if not m:
            raise Exception("Malformed params for FROM: {params}".format(params=params.encode()))
        user, image, tag = m.groups()
        user = user + '/' if user else ''
        tag = tag if tag else 'latest'
        print(user, image, tag)
        
        self.bootstrap = 'docker'
        self.image = '{user}{image}:{tag}'.format(user=user, image=image, tag=tag)

    def RUN(self, params):
        """
        RUN <command>
        RUN ["executable", "param1", "param2", ...]
        """
        if params.startswith('['):
            # RUN [...]
            try:
                s = self.get_list_string(params)
            except:
                raise Exception("Malformed params for RUN: {params}".format(params=params))
            self.post += '\n    ' + ' '.join(s)
        else:
            self.post += '\n    ' + params
    
    def CMD(self, params):
        """
        CMD ["executable","param1","param2"]
        CMD ["param1","param2"]
        CMD command param1 param2
        """
        if params.startswith('['):
            # CMD [...]
            try:
                s = self.get_list_string(params)
            except:
                raise Exception("Malformed params for CMD: {params}".format(params=params))
            self.cmd = s
        else:
            self.cmd = params
    
    def LABEL(self, params):
        """
        LABEL key1="value1 v3" key2=value2
        """
        pairs = self.get_key_value_pairs(params.strip())
        for key, value in pairs:
            self.labels += '\n    {key} {value}'.format(key=key, value=value)
    
    def MAINTAINER(self, params):
        """
        MAINTAINER <name>
        Deprecated and ignored
        """
        return
    
    def EXPOSE(self, params):
        """
        EXPOSE <port> [<port>/<protocol>...]
        Ignored as singularity does not handle networking
        """
        return
    
    def ENV(self, params):
        """
        ENV <key> <value>
        ENV <key>=<value> ...
        """
        for key,value in self.get_key_value_pairs(params):
            # If we have some args then replace them when nessesary
            if value.startswith('$'):
                _tmpvalue = value.replace('$', '')
                if _tmpvalue in self._environment:
                    value = self._environment[_tmpvalue]
            self.post += '\n    echo \'export {key}={value}\' >> $SINGULARITY_ENVIRONMENT'.format(key=key, value=value)
            self.post += '\n    export {key}={value}'.format(key=key, value=value)

    def ADD(self, params):
        """
        ADD [--chown=<user>:<group>] <src>... <dest>
        ADD [--chown=<user>:<group>] ["<src>",... "<dest>"]
        
        ADD hom* /mydir/        # adds all files starting with "hom"
        ADD hom?.txt /mydir/    # ? is replaced with any single character, e.g., "home.txt"
        ADD test relativeDir/          # adds "test" to `WORKDIR`/relativeDir/
        ADD test /absoluteDir/         # adds "test" to /absoluteDir/
        
        We assume the dest is a file (1:1 relation of src and dest)
        TODO sometimes dest is just a dir
        """
        print(' ADD params `{params}`'.format(params=params.strip()))
        regex = r'([\S]+)'  # TODO doesnt allow " or space
        srcs = set()
        dest = None
        while params:
            #print(' ADD params `{params}`'.format(params=params))
            # Get one match, then do it again on the rest of the string
            m = re.match(regex, params)
            if not m:
                raise Exception("Malformed params for ADD: {params}".format(params=params))
            # TODO work in workdir if its not an absolute path
            src, = m.groups()
            
            # Add the current dest as a source, then make the last entry the dest
            if dest:
                srcs.add(dest)
            dest = src
            print("srcs: `{srcs}`; dest: `{dest}`".format(srcs=srcs, dest=dest))

            params = params[m.span()[1]:].strip()
            
        print("Downloading `{dest}` from `{docker_image_name}`".format(dest=dest, docker_image_name=shlex.quote(self.docker_image_name)))
        # Make sure the image is pulled
        subprocess.run("docker pull {docker_image_name}".format(docker_image_name=shlex.quote(self.docker_image_name)).split())
        
        # TODO do we care to preserve the folder structure of /src? We might if people have the same filename if different folders, but lets skip that for now
        # TODO need to work in workdir, get that working. We currently assume that dest starts with a /
        cmd = "docker run --rm --entrypoint cat {docker_image_name} {dest}"
        
        try:
            # First try to just get the destination. If might be a file and this will just work
            names = [dest]
            print("Downloading: {names}".format(names=names))
            files = [(s, subprocess.run(cmd.format(dest=s, docker_image_name=shlex.quote(self.docker_image_name)).split(), stdout=subprocess.PIPE)) for s in names]
            # On linux this raised an error, on windows it didnt, so lets check to be sure
            for path, process in files:
                process.check_returncode()
            self.setup += '\n    mkdir -p $SINGULARITY_ROOTFS/{dest}'.format(dest=os.path.dirname(dest))
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Its a folder, we need to empty the contents
            # TODO figure out how to get multiple out of wildcards and whatnot
            names = [os.path.join(dest,s) for s in srcs]
            print("Scratch that, downloading: {names}".format(names=names))
            files = [(s, subprocess.run(cmd.format(dest=s, docker_image_name=shlex.quote(self.docker_image_name)).split(), stdout=subprocess.PIPE)) for s in names]
            self.setup += '\n    mkdir -p $SINGULARITY_ROOTFS/{dest}'.format(dest=dest)
            
        for path, process in files:
            process.check_returncode()
            basename = os.path.basename(path)
            print("Path: `{path}`; basename: {basename}".format(path=path, basename=basename))
            with open(os.path.join(shlex.quote(self.folder), basename), 'wb') as f:
                f.write(process.stdout)

            self.files += "\n    {basename} {dest}".format(basename=basename, dest=dest)
        
    def COPY(self, params):
        return self.ADD(params)
    
    def ENTRYPOINT(self, params):
        """
        ENTRYPOINT ["executable", "param1", "param2"] (exec form, preferred)
        ENTRYPOINT command param1 param2 (shell form)
        """
        if params.startswith('['):
            # ENTRYPOINT [...]
            try:
                s = self.get_list_string(params)
            except:
                raise Exception("Malformed params for ENTRYPOINT: {params}".format(params=params))
            self.entrypoint = s
        else:
            # ENTRYPOINT ...
            self.entrypoint = params
    
    def VOLUME(self, params):
        """
        VOLUME ["/data"]
        VOLUME /var/log /var/db
        """
        # TODO what do I do here?
        return
    
    def USER(self, params):
        """
        USER <user>[:<group>] or
        USER <UID>[:<GID>]
        No need to change user, ignored
        """
        return
    
    def WORKDIR(self, params):
        """
        WORKDIR /path/to/workdir
        """
        self.workdir = params
    
    def ONBUILD(self, params):
        """
        ONBUILD ADD . /app/src
        ONBUILD RUN /usr/local/bin/python-build --dir /app/src
        Currently Ignored
        """
        # TODO not sure what to do here either
        return
    
    def STOPSIGNAL(self, params):
        """
        STOPSIGNAL signal
        Currently ignored
        """
        return
    
    def HEALTHCHECK(self, params):
        """
        HEALTHCHECK [OPTIONS] CMD command
        HEALTHCHECK NONE
        Currently ignored
        """
        return
    
    def SHELL(self, params):
        """
        SHELL ["executable", "parameters"]
        Currently Ignored
        """
        return
