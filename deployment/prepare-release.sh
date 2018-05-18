#!/bin/bash

#CB_REPOS="connectbox-pi NEO_BatteryLevelShutdown connectbox-react-icon-client connectbox-reports"
GITHUB_OWNER="ConnectBox"
CB_REPOS="server-services"
MAIN_REPO="server-services"

generate_version_string() {
	echo "v$(date +%Y%m%d%H%M%S)"
}

checkout_and_tag() {
	for repo in ${CB_REPOS}; do
		echo $repo;
		git clone --depth=1 git@github.com:${GITHUB_OWNER}/${repo}.git
		git -C ${repo} tag $VERSION
		git -C ${repo} push --tags
	done
}

create_release() {
	# Create release for the appropriate tag, in the main repo
	API_JSON=$(printf '{"tag_name": "%s","target_commitish": "master","name": "%s","body": "Release of version %s","draft": true,"prerelease": true}' $VERSION $VERSION $VERSION)
	reply=$(curl --silent --data "$API_JSON" https://api.github.com/repos/${GITHUB_OWNER}/${MAIN_REPO}/releases?access_token=${CONNECTBOX_GITHUB_TOKEN})

	if [ "$?" -ne 0 ]; then
		echo "Release not created"
		echo $reply
		exit 1
	fi

	rel_url=$(echo $reply | jq .html_url)
	echo "Pre-release, draft release created in ${MAIN_REPO} at ${rel_url}"
}

VERSION=$(generate_version_string)
checkout_and_tag
create_release
