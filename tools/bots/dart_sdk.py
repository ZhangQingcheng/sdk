#!/usr/bin/env python
#
# Copyright (c) 2015, the Dart project authors.  Please see the AUTHORS file
# for details. All rights reserved. Use of this source code is governed by a
# BSD-style license that can be found in the LICENSE file.

import os.path
import shutil
import sys

import bot
import bot_utils

utils = bot_utils.GetUtils()

BUILD_OS = utils.GuessOS()

(bot_name, _) = bot.GetBotName()
CHANNEL = bot_utils.GetChannelFromName(bot_name)

def BuildSDK():
  with bot.BuildStep('Build SDK'):
    Run([sys.executable, './tools/build.py', '--mode=release',
         '--arch=ia32,x64', 'create_sdk'])

def BuildAPIDocs():
  with bot.BuildStep('Build API docs'):
    Run([sys.executable, './tools/build.py', '--mode=release',
         '--arch=ia32', 'api_docs'])
    Run([sys.executable, './tools/build.py', '--mode=release',
         '--arch=ia32', 'dartdocgen'])

def CreateUploadVersionFile():
  file_path = os.path.join(bot_utils.DART_DIR,
                           utils.GetBuildRoot(BUILD_OS, 'release', 'ia32'),
                           'VERSION')
  with open(file_path, 'w') as fd:
    fd.write(utils.GetVersionFileContent())
  DartArchiveUploadVersionFile(file_path)

def DartArchiveUploadVersionFile(version_file):
  namer = bot_utils.GCSNamer(CHANNEL, bot_utils.ReleaseType.RAW)
  revision = utils.GetArchiveVersion()
  for revision in [revision, 'latest']:
    destination = namer.version_filepath(revision)
    DartArchiveFile(version_file, destination, checksum_files=False)

def CreateUploadSDKZips():
  with bot.BuildStep('Create and upload sdk zips'):
    sdk32_path = os.path.join(bot_utils.DART_DIR,
                              utils.GetBuildRoot(BUILD_OS, 'release', 'ia32'),
                              'dart-sdk')
    sdk64_path = os.path.join(bot_utils.DART_DIR,
                              utils.GetBuildRoot(BUILD_OS, 'release', 'x64'),
                              'dart-sdk')

    sdk32_zip = os.path.join(bot_utils.DART_DIR,
                             utils.GetBuildRoot(BUILD_OS, 'release', 'ia32'),
                             'dartsdk-%s-32.zip' % BUILD_OS)
    sdk64_zip = os.path.join(bot_utils.DART_DIR,
                             utils.GetBuildRoot(BUILD_OS, 'release', 'x64'),
                             'dartsdk-%s-64.zip' % BUILD_OS)
    FileDelete(sdk32_zip)
    FileDelete(sdk64_zip)
    CreateZip(sdk32_path, sdk32_zip)
    CreateZip(sdk64_path, sdk64_zip)
    DartArchiveUploadSDKs(BUILD_OS, sdk32_zip, sdk64_zip)

def DartArchiveUploadSDKs(system, sdk32_zip, sdk64_zip):
  namer = bot_utils.GCSNamer(CHANNEL, bot_utils.ReleaseType.RAW)
  revision = utils.GetArchiveVersion()
  for revision in [revision, 'latest']:
    path32 = namer.sdk_zipfilepath(revision, system, 'ia32', 'release')
    path64 = namer.sdk_zipfilepath(revision, system, 'x64', 'release')
    DartArchiveFile(sdk32_zip, path32, checksum_files=True)
    DartArchiveFile(sdk64_zip, path64, checksum_files=True)

def CreateUploadSDK():
  BuildSDK()
  CreateUploadSDKZips()

def CreateUploadAPIDocs():
  api_path = os.path.join(bot_utils.DART_DIR,
                          utils.GetBuildRoot(BUILD_OS, 'release', 'ia32'),
                          'api_docs')
  api_zip = os.path.join(bot_utils.DART_DIR,
                         utils.GetBuildRoot(BUILD_OS, 'release', 'ia32'),
                         'dart-api-docs.zip')
  shutil.rmtree(api_path, ignore_errors=True)
  FileDelete(api_zip)
  BuildAPIDocs()
  UploadApiDocs(api_path)
  CreateZip(api_path, api_zip)
  DartArchiveUploadAPIDocs(api_zip)

def DartArchiveUploadAPIDocs(api_zip):
  namer = bot_utils.GCSNamer(CHANNEL, bot_utils.ReleaseType.RAW)
  revision = utils.GetArchiveVersion()
  for revision in [revision, 'latest']:
    destination = (namer.apidocs_directory(revision) + '/' +
        namer.apidocs_zipfilename())
    DartArchiveFile(api_zip, destination, checksum_files=False)

def UploadApiDocs(dir_name):
  apidocs_namer = bot_utils.GCSNamerApiDocs(CHANNEL)
  revision = utils.GetArchiveVersion()
  apidocs_destination_gcsdir = apidocs_namer.docs_dirpath(revision)
  apidocs_destination_latestfile = apidocs_namer.docs_latestpath(revision)

  # Return early if the documents have already been uploaded.
  # (This can happen if a build was forced, or a commit had no changes in the
  # dart repository (e.g. DEPS file update).)
  if GsutilExists(apidocs_destination_gcsdir):
    print ("Not uploading api docs, since %s is already present."
           % apidocs_destination_gcsdir)
    return

  # Upload everything inside the built apidocs directory.
  gsutil = bot_utils.GSUtil()
  gsutil.upload(dir_name, apidocs_destination_gcsdir, recursive=True,
                public=True)

  # Update latest.txt to contain the newest revision.
  with utils.TempDir('latest_file') as temp_dir:
    latest_file = os.path.join(temp_dir, 'latest.txt')
    with open(latest_file, 'w') as f:
      f.write('%s' % revision)
    DartArchiveFile(latest_file, apidocs_destination_latestfile)

def GsutilExists(gsu_path):
  # This is a little hackish, but it is basically a one off doing very
  # specialized check that we don't use elsewhere.
  gsutilTool = os.path.join(bot_utils.DART_DIR,
                            'third_party', 'gsutil', 'gsutil')
  (_, stderr, returncode) = bot_utils.run(
      [gsutilTool, 'ls', gsu_path],
      throw_on_error=False)
  # If the returncode is nonzero and we can find a specific error message,
  # we know there are no objects with a prefix of [gsu_path].
  missing = (returncode and 'CommandException: No such object' in stderr)
  # Either the returncode has to be zero or the object must be missing,
  # otherwise throw an exception.
  if not missing and returncode:
    raise Exception("Failed to determine whether %s exists" % gsu_path)
  return not missing


def CreateZip(directory, target_file):
  if 'win' in BUILD_OS:
    CreateZipWindows(directory, target_file)
  else:
    CreateZipPosix(directory, target_file)

def CreateZipPosix(directory, target_file):
  with utils.ChangedWorkingDirectory(os.path.dirname(directory)):
    command = ['zip', '-yrq9', target_file, os.path.basename(directory)]
    Run(command)

def CreateZipWindows(directory, target_file):
  with utils.ChangedWorkingDirectory(os.path.dirname(directory)):
    zip_win = os.path.join(bot_utils.DART_DIR, 'third_party', '7zip', '7za')
    command = [zip_win, 'a', '-tzip', target_file, os.path.basename(directory)]
    Run(command)

def FileDelete(f):
  if os.path.exists(f):
    os.remove(f)

def DartArchiveFile(local_path, remote_path, checksum_files=False):
  gsutil = bot_utils.GSUtil()
  gsutil.upload(local_path, remote_path, public=True)
  if checksum_files:
    # 'local_path' may have a different filename than 'remote_path'. So we need
    # to make sure the *.md5sum file contains the correct name.
    assert '/' in remote_path and not remote_path.endswith('/')

    mangled_filename = remote_path[remote_path.rfind('/') + 1:]
    local_md5sum = bot_utils.CreateMD5ChecksumFile(local_path,
                                                   mangled_filename)
    gsutil.upload(local_md5sum, remote_path + '.md5sum', public=True)
    local_sha256 = bot_utils.CreateSha256ChecksumFile(local_path,
                                                      mangled_filename)
    gsutil.upload(local_sha256, remote_path + '.sha256sum', public=True)

def Run(command):
  print "Running %s" % ' '.join(command)
  return bot.RunProcess(command)

if __name__ == '__main__':
  # We always clobber the bot, to make sure releases are build from scratch
  force = CHANNEL != bot_utils.Channel.BLEEDING_EDGE
  bot.Clobber(force=force)

  CreateUploadSDK()
  if BUILD_OS == 'linux':
    CreateUploadVersionFile()
    CreateUploadAPIDocs()
