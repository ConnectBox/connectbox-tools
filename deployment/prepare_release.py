#!/usr/bin/env python2
"""
Drive release process for connectbox images
"""

from datetime import datetime
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import click
from github import Github


CONNECTBOX_REPOS = [
    "connectbox-pi",
    "NEO_BatteryLevelShutdown",
    "connectbox-react-icon-client",
    "access-log-analyzer",
    "simple-offline-captive-portal",
]
# while testing
#CONNECTBOX_REPOS = ["server-services"]
GITHUB_OWNER = "ConnectBox"
#MAIN_REPO = "server-services"
MAIN_REPO = "connectbox-pi"

NEO_TYPE = "NanoPi NEO"
RPI_TYPE = "Raspberry Pi"
UNKNOWN_TYPE = "??"


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
    release = gh_repo.create_git_release(
        tag,
        tag,
        "Insert release notes here",
        draft=True,
        prerelease=True
    )
    return release


def checkout_ansible_repo(tag):
    repo = "connectbox-pi"
    click.secho("Deleting previous %s build directory" % (repo,),
                fg="blue", bold=True)
    shutil.rmtree(repo)

    repo_addr = "https://github.com/ConnectBox/connectbox-pi.git"
    subprocess.run(
        ["git", "clone", "-b", tag, "--depth=1", repo_addr],
        check=True
    )
    return repo

def device_type_from_model_str(model_str):
    if NEO_TYPE in model_str:
        return NEO_TYPE
    elif RPI_TYPE in model_str:
        return RPI_TYPE

    return UNKNOWN_TYPE


def get_device_ip_and_type():
    device_addr = ""
    while not device_addr:
        text = click.style("Enter IP address for build device",
                           fg="blue", bold=True)
        response = click.prompt(text)
        try:
            device_addr = ipaddress.ip_address(response)
        except ValueError as val:
            click.secho(val.args[0], fg="blue", bold=True)
            device_addr = ""

    # We don't care about known hosts given we touch a new device each time
    known_hosts = Path("~/.ssh/known_hosts").expanduser()
    if known_hosts.exists():
        known_hosts.unlink()

    can_ssh_to_device = False
    device_type = UNKNOWN_TYPE
    while not can_ssh_to_device:
        click.secho("Ready to attempt passwordless ssh to %s" % (device_addr,),
                    fg="blue", bold=True)
        click.pause()
        try:
            proc = subprocess.run([
                "ssh",
                "-oStrictHostKeyChecking=no",
                "-l",
                "root",
                device_addr.exploded,
                "cat /sys/firmware/devicetree/base/model"
                ], check=True, stdout=subprocess.PIPE)
            device_type = \
                device_type_from_model_str(proc.stdout.decode("utf-8"))
            can_ssh_to_device = True
        except subprocess.CalledProcessError as cpe:
            click.secho(cpe.args, fg="blue", bold=True)

    click.secho("Deploying to %s (type: %s)" %
                (device_addr.exploded, device_type), bold=True)
    return device_addr.exploded, device_type


def create_inventory(device_ip):
    click.secho("Creating ansible inventory", fg="blue", bold=True)
    inventory_str = \
        "%s deploy_sample_content=False do_image_preparation=True\n" % \
        (device_ip,)
    inventory_fd, inventory_name = tempfile.mkstemp()
    os.pwrite(inventory_fd, inventory_str.encode("utf-8"), 0)
    os.close(inventory_fd)
    return inventory_name


def run_ansible(inventory, tag, repo_location):
    click.secho("Running ansible", fg="blue", bold=True)
    # release builds always run with the root account, even on raspbian.
    # the ansible_user here overrides the group_vars/raspbian variables
    subprocess.run(
        ["ansible-playbook",
         "-i",
         inventory,
         "-e",
         "ansible_user=root",
         "-e",
         "connectbox_version=%s" % (tag,),
         "site.yml"
        ], cwd=os.path.join(repo_location, "ansible")
    )


def create_img_from_sd(tag, device_type):
    with open("/proc/partitions") as proc_partitions:
        partitions_before = proc_partitions.read()

    click.secho("Attach SD card from device", fg="blue", bold=True)
    # look for sdb1$ in the last line of /proc/partitions
    # perhaps prompt?
    sd_seen_in_dmesg = False
    while not sd_seen_in_dmesg:
        sd_seen_in_dmesg = click.confirm("Has SD appeared as /dev/sdb in dmesg?")

    with open("/proc/partitions") as proc_partitions:
        partitions_after = proc_partitions.read()

    print("sdb1 in partitions_before? %s" % ("sdb1" in partitions_before,))
    print("sdb1 in partitions_after? %s" % ("sdb1" in partitions_after,))
    print("before: %s", (partitions_before,))
    print("after: %s", (partitions_after,))
    click.pause()
    path_to_image = "/tmp/%s_%s.img" % (device_type.replace(" ", "-"), tag,)
    subprocess.run(
        ["sudo",
         "/vagrant/shrink-image.sh",
         "/dev/sdb",
         path_to_image
        ]
    )
    return path_to_image


def compress_img(path_to_image):
    path_to_compressed_image = os.path.join(
        "/vagrant",
        "%s.7z" % (os.path.basename(path_to_image),)
    )
    cmd = ["7za",
           "a",
           "-t7z",
           "-m0=lzma",
           "-mx=9",
           "-mfb=64",
           "-md=32m",
           "-ms=on",
           path_to_compressed_image,
           path_to_image
          ]
    subprocess.run(cmd)
    return path_to_compressed_image


@click.command()
@click.option("--github-token",
              prompt=True,
              default=lambda: os.environ.get("CONNECTBOX_GITHUB_TOKEN", ""),
              help="Github token with ConnectBox org write privs")
@click.option("--tag",
              prompt="Enter tag for this release",
              default=lambda: datetime.utcnow().strftime("v%Y%m%d"),
              help="Name of this release (also used as git tag)")
@click.option("--use-existing-tag",
              is_flag=True,
              default=False,
              help="Use an existing tag and do not tag the repos")
def main(github_token, tag, use_existing_tag):
    # do things early that prompt
    device_ip, device_type = get_device_ip_and_type()
    connectbox_org = Github(github_token).get_organization("ConnectBox")
    if not use_existing_tag:
        text = click.style("Proceed with new tag '%s'?" % (tag,),
                           fg="blue", bold=True)
        click.confirm(text, abort=True)
        create_tags_in_repos(connectbox_org, CONNECTBOX_REPOS, tag)
        gh_release = create_github_release(connectbox_org.get_repo(MAIN_REPO), tag)
    else:
        text = click.style("Proceed with existing tag '%s'?" % (tag,),
                           fg="blue", bold=True)
        click.confirm(text, abort=True)
        # connectbox_org.get_repo(MAIN_REPO).get_release(tag) doesn't find
        #  draft releases, but all releases does, so let's use that
        gh_release = [
            r for r in connectbox_org.get_repo(MAIN_REPO).get_releases()
            if r.title == tag
        ][0]

    repo_location = checkout_ansible_repo(tag)
    # install packages needed for connectbox build
    subprocess.run(
        ["pip3",
         "install",
         "-r",
         os.path.join(repo_location, "requirements.txt")
        ]
    )
    inventory_name = create_inventory(device_ip)
    run_ansible(inventory_name, tag, repo_location)
    img_name = create_img_from_sd(tag, device_type)
    path_to_compressed_image = compress_img(img_name)
    click.secho("Compressed image complete and located at: %s" %
                (path_to_compressed_image,), fg="blue", bold=True)
    click.secho("Uploading to Github (may take ~1hr). Check progress in the "
                "github release page itself", fg="blue", bold=True)
    gh_release.upload_asset(path_to_compressed_image)
    click.secho("Now, update release notes, inserting changelog and base "
                "image name", fg="blue", bold=True)


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
