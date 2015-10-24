#!/usr/bin/python

from itertools import chain
flatten = chain.from_iterable
from multiprocessing import Pool, cpu_count
from os.path import dirname, exists, join
from sys import stdin

import yamlconfig   # partly configargparse
import configsearch # xdg.BaseDirectory.load_config_paths('byod')
import gitcache
import yamldoctree
import brdefinitions
import artifactcache
import sandboxlib

# Generates a config file parser
parser = yamlconfig.load(join(dirname(m.__file__), 'config-schema.yaml')
                         for m in (gitcache, artifactcache, sandboxlib)
                         if exists(join(dirname(m.__file__),
                                        'config-schema.yaml'))
# Generates a command-line parser
parser = parser.parse_files(configsearch.find_config('byod'))
options = parser.parse_argv()

build_graph = brdefinitions.deserialize_build_graph(stdin)
assert set(build_graph.find_leaves()) >= set(build_graph.find_targets())


def determine_parallelism(options):
	nprocs = floor(cpu_count() / options.localbuild.cpus_per_process) or 1
	maxjobs = cpu_count() / nprocs
	return nprocs, maxjobs


def log_build_progress(response_queue):
	'Report lines from the queue to stdout, terminates on None sentinel.'
	for build_name, message in iter(response_queue.get(), None):
		if message[0] == 'returncode':
			stdout.write(
				'{} Finished:\t{}'.format(build_name, message[1]))
		elif message[0] in ('stdout', 'stderr'):
			stdout.write(
				'{} {}:\t{}'.format(
					build_name, message[0][3:].upper():,
					message[1]))
		else:
			assert False

def report_progress(p, build_name, reponse_queue):
	'''Report p's stdout and stderr

	   Selects on p.stdout and p.stderr, buffering the output lines
	   and putting them in the response_queue, so that another
	   process can listen to it and report build status.

	   The response_queue is shared, so the build_name is included
	   in the messages.

	   When stdout and stderr EOF, the last of the output and the
	   return code is communicated in the response_queue.

	   A combined result of the stdout and stderr is returned.
	'''
	pass

# Artifact cache may async upload, compress, gc.
# TODO: Should it block or cancel on fail?
with artifactcache.load(options.artifactcache) as artifact_cache:
	if not all(artifact_cache.has(artifact)
	           for artifact in build_graph.find_targets()):

		nprocs, maxjobs = determine_parallelism(options)
		pool = Pool(processes=nprocs)

		response_manager = Manager()
		response_queue = response_manager.Queue()

		def buildone(response_queue, build_name
		             artifact_cache_config_argv,
		             git_cache_config_argv, max_jobs, cache_id,
		             split_rules, artifact_dependencies, source,
		             build_mode, commands):
			# Transforms:
			# - shell: ./configure
			# - shell: MAKEFLAGS="-j$VIRTPARALLELJOBCOUNT" && export MAKEFLAGS && make
			#   set-virtual-parallelism: VIRTPARALLELJOBCOUNT
			# - shell: make DESTDIR="$DESTDIR" install
			#   set-destdir: DESTDIR
			# Into:
			# - shell: ./configure
			# - shell: MAKEFLAGS="-j$VIRTPARALLELJOBCOUNT" && export MAKEFLAGS && make
			#   env:
			#     VIRTPARALLELJOBCOUNT: 4 # guaranteed parallel
			# - shell: make DESTDIR="$DESTDIR" install
			#   env:
			#     DESTDIR: /foo.inst
			with NamedTemporaryFile() as input_commands_f, \
			     NamedTemporaryFile() as output_artifacts_list_f:
				yaml.dump({}, commands_f)
				argv = list(
					chain(('byod-buildone.py',),
					      artifact_cache_config_argv,
					      git_cache_config_argv,
					      ('--dependent-artifact' + a
					       for a in artifact_dependencies),
					      ('--build-dir',
					       '/%s.build' % build_name),
					      ('--source-repo', source['repo-url'],
					       '--source-tree', source['tree']),
					      (('--bootstrap',)
					       if build_mode == 'bootstrap' else ()),
					      ('--dest-dir',
					       '/%s.inst' % build_name),
					      ('--read-commands-from',
					       input_commands_f.name),
					      ('--artifacts',
					       output_artifacts_list_f.name),
					))
				p = Popen(argv, stdin=open(devnull), stdout=PIPE,
				          stderr=PIPE)
				log = report_progress(p, build_name,
				                      response_queue)
				if p.returncode:
					raise BuildFailure(argv, p.returncode,
					                   log)
				return yaml.load(output_artifacts_list_f)

		outhandler = Thread(target=log_build_progress,
		                    args=(response_queue,),
		                    name='Build output logging')
		outhandler.daemon = True
		outhandler.start()

		produced_artifacts = set()

		def get_buildargs(s):
			return (response_queue, s.cacheid,
			        options.artifactcache.as_argv(),
			        options.git_cache_config.as_argv(),
			        s.max_jobs, s.cache_id, s.split_rules,
			        tuple(s.dependent_artifacts),
			        {'repo-url': s.repo_url, 'tree': s.tree},
			        s.build_mode,
			        s.commands)
		try:
			for produced_artifacts in pool.imap_unordered(
				lambda s: buildone(*get_buildargs(s)),
				build_graph.depth_first_sources()):

				artifact_cache.maybe_async_upload_artifacts(
					produced_artifacts)
		except BaseException as e:
			pool.terminate()
			raise
		else:
			pool.close()
		finally:
			response_queue.put(None)
			pool.join()
			outhandler.join()
