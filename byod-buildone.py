#!/usr/bin/python

'''Build a single thing.

Set up a staging area by loading artifacts out of the artifact cache,
copying a source tree out of the git cache into the staging area build-dir,
requesting to create a new artifact (so the cache can lock or do 0-copy magic),
running a specified sequence of sandboxed commands

'''


__version__ = '0.0.0'


from xdg.BaseDirectory import save_cache_path


def initialize_argument_parser(parser):
	# Artifact cache config
	parser.add_argument('--artifact-cache-dir',
	                    default=save_cache_path('byod', 'artifacts'))
	parser.add_argument('--git-cache-dir',
	                    default=save_cache_path('byod', 'gits'))
	parser.add_argument('--dependent-artifact', nargs='*')

if __name__ == '__main__':
        from argparse import ArgumentParser # TODO: use declarative config
	parser = ArgumentParser(description=__doc__)
	parser.add_argument('--version', action='version',
	                    version=('%(prog)s ' + __version__))
	initialize_argument_parser(parser)
	print(parser.parse_args())
