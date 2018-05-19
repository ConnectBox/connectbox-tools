#!/bin/bash

set -e

#CB_REPOS="connectbox-pi NEO_BatteryLevelShutdown connectbox-react-icon-client connectbox-reports"
GITHUB_OWNER="ConnectBox"
CB_REPOS="server-services"
MAIN_REPO="server-services"

generate_tag_string() {
	#default_tag="v$(date +%Y%m%d)"
	default_tag="v$(date +%Y%m%d%H%M%S)"
	read -p "Enter tag name for this release [$default_tag]: "
	if [ -z "$REPLY" ]; then
		tag=$default_tag;
	else
		tag=$REPLY
	fi
	read -p "Proceed with tag \"$tag\" [y/N]: "
	if [ "$REPLY" != "y" -a "$REPLY" != "Y" ]; then
	  echo "OK, not proceeding."
		return 1;
	fi
	echo $tag;
}

checkout_and_tag() {
	for repo in ${CB_REPOS}; do
		echo "Cloning and tagging: $repo";
		if [ -d "${repo}" ]; then
			echo "Repo already exists locally. Cannot proceed"
			return 1;
		fi
		git clone --quiet --depth=1 git@github.com:${GITHUB_OWNER}/${repo}.git
		# git will bomb if the tag already exists, so no extra logic is required
		git -C ${repo} tag $TAG
		git -C ${repo} push --tags
	done
}

create_release() {
	# Create release for the appropriate tag, in the main repo
	# FIXME - API doesn't prevent releases with duplicate names, so need logic here
	#  to prevent that.
	API_JSON=$(printf '{"tag_name": "%s","target_commitish": "master","name": "%s","body": "Release of tag %s","draft": true,"prerelease": true}' $TAG $TAG $TAG)
	reply=$(curl --silent --data "$API_JSON" https://api.github.com/repos/${GITHUB_OWNER}/${MAIN_REPO}/releases?access_token=${CONNECTBOX_GITHUB_TOKEN})

	if [ "$?" -ne 0 ]; then
		echo "Release not created"
		echo $reply
		exit 1
	fi

	rel_url=$(echo $reply | jq .html_url)
	echo "Pre-release, draft release created in ${MAIN_REPO} at ${rel_url}"
}

do_one_image() {
	default_device_type="nanopi-neo"
	device_type=""
	acceptable_device_types=(nanopi-neo orange-pi-zero-plus2 raspberrypi)
	read -p "Enter device type [$default_device_type]: "

}
TAG=$(generate_tag_string)
checkout_and_tag
create_release

read -p "Run ansible in another window to build a device. Press ENTER when you're ready to import the image"
