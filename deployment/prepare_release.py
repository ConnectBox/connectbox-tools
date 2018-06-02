#!/usr/bin/env python3
"""
Drive release process for connectbox images
"""

from datetime import datetime
import ipaddress
import os
import subprocess
import sys
from github import Github


CONNECTBOX_REPOS = [
    "connectbox-pi",
    "NEO_BatteryLevelShutdown",
    "connectbox-react-icon-client",
    "connectbox-reports",
]
# while testing
#CONNECTBOX_REPOS = ["server-services"]
GITHUB_OWNER = "ConnectBox"
#MAIN_REPO = "server-services"
MAIN_REPO = "connectbox-pi"


def get_env_variable(var_name):
    """ Get the environment variable or return exception """
    try:
        return os.environ[var_name]
    except KeyError:
        error_msg = "Set the %s env variable" % var_name
        raise RuntimeError(error_msg)


def generate_tag_string():
    default_tag = datetime.utcnow().strftime("v%Y%m%d")
    # while testing
    # default_tag = datetime.utcnow().strftime("v%Y%m%d%H%M%S")
    tag = input("Enter tag name for this release [%s]: " % (default_tag,))
    if not tag:
        tag = default_tag

    response = input("Proceed with tag '%s'? [y/N]: " % (tag,))
    if response.lower() != "y":
        print("OK, not proceeding")
        sys.exit(0)
    return tag


def create_tags_in_repos(connectbox_org, repos, tag):
    for repo in repos:
        gh_repo = connectbox_org.get_repo(repo)
        most_recent_commit = gh_repo.get_commits()[0]
        gh_repo.create_git_tag(
            tag,
            "Automated git tag during connectbox release",
            most_recent_commit.sha,
            "commit"
        )
        # We only have a lightweight tag so far. Make it an annotated tag
        gh_repo.create_git_ref("refs/tags/%s" %
                               (tag,), most_recent_commit.sha
                              )

def create_github_release(gh_repo, tag):
    gh_repo.create_git_release(
        tag,
        tag,
        "Insert release notes here",
        draft=True,
        prerelease=True
    )


def checkout_ansible_repo(tag):
    repo = "connectbox-pi"
    if os.path.isdir(repo):
        print("Repo already exists locally. Cannot proceed")
        sys.exit(1)

    # XXX - use https so that we don't need to have github key
    # repo_addr = "git@github.com:%s/%s.git" % (GITHUB_OWNER, repo)
    repo_addr = "https://github.com/ConnectBox/connectbox-pi.git"
    # XX - while developing
    #tag = "v20180418"
    subprocess.run(
        ["git", "clone", "-b", tag, "--depth=1", repo_addr],
        check=True
    )

def prepare_for_ansible():
    device_addr = ""
    while not device_addr:
        response = input("Enter IP address for build device: ")
        try:
            device_addr = ipaddress.ip_address(response)
        except ValueError as val:
            print(val.args[0])
            device_addr = ""

    can_ssh_to_device = False
    while not can_ssh_to_device:
        response = input(
            "Ready to attempt passwordless ssh to %s. Enter to start: " %
            (device_addr,)
        )
        try:
            subprocess.run([
                "ssh",
                "-l",
                "root",
                device_addr.exploded,
                "/bin/true"], check=True)
            can_ssh_to_device = True
        except subprocess.CalledProcessError as cpe:
            print(cpe.args)

    return device_addr


def run_ansible(device_addr, tag):
    print("Run: ansible-playbook -u root -i inventory site.yml "
          "-e connectbox_version=%s "
          "-e developer_mode=True "
          "-e deploy_sample_content=False "
          "-e do_image_preparation=True "
          "--limit=%s" %
          (tag, device_addr)
         )


def create_img_from_sd(tag):
    print("Attach SD card from device and confirm it appears as /dev/sdb "
          "(check dmesg)")
    # XXX could look to find which model automatically eventually
    img_name = "nanopi-neo_developer_%s.img" % (tag,)
    print("sudo /vagrant/shrink-image.sh /dev/sdb ./%s" % (img_name,))
    return img_name


def compress_img(img_name):
    print("7za a -t7z -m0=lzma -mx=9 -mfb=64 -md=32m -ms=on "
          "/vagrant/%s.7z ./%s" % (img_name, img_name))


def main():
    github_token = get_env_variable("CONNECTBOX_GITHUB_TOKEN")
    connectbox_org = Github(github_token).get_organization("ConnectBox")
    tag = generate_tag_string()
    create_tags_in_repos(connectbox_org, CONNECTBOX_REPOS, tag)
    create_github_release(connectbox_org.get_repo(MAIN_REPO), tag)
    checkout_ansible_repo(tag)
    device_addr = prepare_for_ansible()
    run_ansible(device_addr, tag)
    img_name = create_img_from_sd(tag)
    print("Now, update release notes, inserting changelog and base image name")



if __name__ == "__main__":
    main()
