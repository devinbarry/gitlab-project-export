import yaml
import os
import sys
from contextlib import contextmanager


class Config:
    """Load configuration from yaml file"""

    def __init__(self, config_file):
        """Init config object"""
        self.config_file = config_file
        self.config = self.load_config()

    @contextmanager
    def open_config_file(self):
        try:
            conf_fh = open(self.config_file, 'r')
            yield conf_fh
        except IOError as e:
            print(f"({e})", file=sys.stderr)
            sys.exit(1)
        finally:
            conf_fh.close()

    def load_config(self):
        with self.open_config_file() as conf_fh:
            config = yaml.load(conf_fh.read(), Loader=yaml.FullLoader)
            self.process_config(config)
            return config

    def process_config(self, config):
        """ Process configuration file, mainly to maintain backwards compatibility of new features """
        ssl_verify_default = True
        gitlab_config = config.setdefault('gitlab', {}).setdefault('access', {})
        gitlab_config.setdefault('ssl_verify', ssl_verify_default)

        # Better safe than sorry. If file or directory not exist set default
        if isinstance(gitlab_config['ssl_verify'], str):
            if not os.path.exists(gitlab_config['ssl_verify']):
                print(f"WARNING: provided path to ssl bundle not exist, setting to {ssl_verify_default}", file=sys.stderr)
                gitlab_config['ssl_verify'] = ssl_verify_default
