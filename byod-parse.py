#!/usr/bin/python

from sys import stdout

import yamlconfig
import configsearch
import gitcache
import yamldoctree
import brdefinitions

# Generates a config file parser
parser = yamlconfig.load(join(dirname(m.__file__), 'config-schema.yaml')
                         for m in (gitcache, yamldoctree, brdefinitions)
                         if exists(join(dirname(m.__file__),
                                        'config-schema.yaml'))
# Generates a command-line parser
parser = parser.parse_files(configsearch.find_config('byod'))
options = parser.parse_argv()

with brdefinitions.load_file_tree(options) as filetree:
	yaml_tree = yamldoctree.YAMLTree(filetree)
	defs = brdefinitions.Definitions(yaml_tree)
	# Resolve refs and generate instructions,
	# including cache IDs for produced artifacts.
	with gitcache.load(options.gitcache) as git_cache:
		build_graph = defs.resolve_build_graph(options.targets, git_cache)

build_graph.serialize(stdout)
