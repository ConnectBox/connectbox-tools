#!/bin/bash
#
#  connectbox image shrinker
#
#  This program will shrink an sd card filesystem
#  to the minimum size, prep it for deployment, and
#  make an image that can be copied to new devices.
#
#  Usage: shrink-image.sh /dev/sdb connectbox.img
# 
#  /dev/sdb is the sd card block device
#  connectbox.img will be the resulting image
#
#  Use with care! Although it makes some effort
#  to ensure you select the correct device, it
#  may correct your OS disk with invalid input!!
#

# sd card device
sd_devpath=$1

# output image file
output_img=$2

# check for empty inputs
if [ "x$sd_devpath" == "x" ] || [ "x$output_img" == "x" ]; then
  echo "Usage: $0 /dev/sdb connectbox.img"
  exit 1
fi

# Make sure we have root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (or via sudo)" 1>&2
   exit 1
fi

# check for block device
if [ ! -b $sd_devpath ]; then
  echo "$sd_devpath is not a valid device!"
  exit -1
fi

# check for valid output directory
output_dir=$(dirname $output_img)
if [ ! -d $output_dir ]; then
  echo "$output_dir is not a valid directory"
  exit -1
fi

# make sure we won't overwrite an existing image
if [ -f $output_img ]; then
  echo "$output_img already exists!"
  exit -1
fi

# make sure device is removable
sd_blkdev=$(basename $sd_devpath)
sd_sysfs=/sys/block/${sd_blkdev}
sd_removable=$(cat $sd_sysfs/removable)
if [ $sd_removable != 1 ]; then
  echo "$sd_devpath is not a removable device (may not be an sd card)"
  exit -1
fi

# make sure device isn't already mounted
# check anything within the device; nothing should be
sd_mounts=$(mount | grep -c "^$sd_devpath")
if [ $sd_mounts -gt 0 ]; then
  echo "$sd_devpath is already mounted!"
  exit -1
fi

# count the device partitions
sd_partcount=$(ls -d ${sd_sysfs}/${sd_blkdev}* | wc -l | tr -d '[:space:]')
if [ $sd_partcount -le 0 ] || [ $sd_partcount -gt 3 ]; then
  echo "$sd_devpath has $sd_partcount partitions (expected 1, 2 or three)"
  exit -1
fi

# if we have one partition, it's root:
if [ $sd_partcount -eq 1 ]; then
  boot_partition_num=0
  boot_sysfs=""
  boot_dev=""

  root_partition_num=1
  root_sysfs=${sd_sysfs}/${sd_blkdev}${root_partition_num}
  root_dev=${sd_devpath}${root_partition_num}
fi

# if we have two partitions, they are probably boot & root:
if [ $sd_partcount -eq 2 ]; then
  boot_partition_num=1
  boot_sysfs=${sd_sysfs}/${sd_blkdev}${boot_partition_num}
  boot_dev=${sd_devpath}${boot_partition_num}

  root_partition_num=2
  root_sysfs=${sd_sysfs}/${sd_blkdev}${root_partition_num}
  root_dev=${sd_devpath}${root_partition_num}
fi


# if we have three partitions, they are probably boot & root & userdata:
if [ $sd_partcount -eq 3 ]; then
  boot_partition_num=1
  boot_sysfs=${sd_sysfs}/${sd_blkdev}${boot_partition_num}
  boot_dev=${sd_devpath}${boot_partition_num}

  root_partition_num=2
  root_sysfs=${sd_sysfs}/${sd_blkdev}${root_partition_num}
  root_dev=${sd_devpath}${root_partition_num}

  user_partition_num=3
  user_sysfs=${sd_sysfs}/${sd_blkdev}${user_partition_num}
  user_dev=${sd_devpath}${user_partition_num}
fi


# make a random temporary path to work in
tmp_path=""
while [ "x$tmp_path" == "x" ]; do
  tmp_path=/tmp/connectbox.$RANDOM
  if [ -d $tmp_path ]; then
    tmp_path=""
  fi
done

# sanity check since an empty path can be dangerous later
if [ "x$tmp_path" == "x" ]; then
  echo "Couldn't generate a unique tmp directory name!"
  exit -1
fi

# create temporary path
mkdir $tmp_path

# make sure it exists...
if [ ! -d $tmp_path ]; then
  echo "Unable to create directory $tmp_path!"
  exit -1
fi

# mount the boot fs and do cleanup
if [ "x$boot_dev" != "x" ]
then
  echo "preparing boot device $boot_dev"
  boot_mount=${tmp_path}/boot
  mkdir -p $boot_mount
  mount $boot_dev $boot_mount

  # Raspbian: make the filesystem expand at the next boot
  if [ -f $boot_mount/cmdline.txt ]
  then
    sed -i 's#\(.\)$#\1 quiet init=/usr/lib/raspi-config/init_resize.sh#' $boot_mount/cmdline.txt
  fi


  fdisk -o Type -l $boot_dev > /tmp/fdisk_out
  a=$(awk '/^Disklabel type: / { print $3 }' /tmp/fdisk_out)
  if [ "dos" ==  "$a" ]
  then
    echo $boot_dev is dos formatted
    dosfsck -a-f-V $boot_dev > /dev/nul 2>&1
  else
    echo $boot_dev is linux formatted
    e2fsck -fy $boot_dev > /dev/null 2>&1
  fi
  sync
  umount $boot_dev

fi

if [ $sd_partcount -gt 0 ]
then
  echo "preparing root device $root_dev"

  fdisk -o Type -l $root_dev > /tmp/fdisk_out
  a= $(awk '/^Disklabel type: / { print $3 }' /tmp/fdisk_out)
  if [ "$a" == "dos" ]
  then
    echo $root_dev is dos formatted
    dosfsck -a-f-V $root_dev > /dev/nul 2>&1
  else
    echo $root_dev is linux formatted
    e2fsck -fy $root_dev > /dev/null 2>&1
  fi
  # make sure the root filesystem is clean

  # mount the root fs for cleanup
  root_mount=${tmp_path}/root
  mkdir -p $root_mount
  mount $root_dev $root_mount

  # clean up any artifacts from provisioning
  rm -rf $root_mount/root/.bash_history
  rm -rf $root_mount/root/.ansible
  rm -rf $root_mount/root/.ssh
  # pip cache
  rm -rf $root_mount/root/.cache

  rm -rf $root_mount/home/pi/.bash_history
  rm -rf $root_mount/home/pi/.ansible
  rm -rf $root_mount/home/pi/.ssh
  # pip cache
  rm -rf $root_mount/home/pi/.cache

  # empty all of the log files!
  find $root_mount/var/log/ -type f | while read file; do
    echo -n > "$file"
  done
  # defragment (should allow for smaller shrinking) i
  echo "defragmenting $root_dev... (this may take a while)"
  e4defrag $root_dev

  # unmount the filesystems preparing for shrinking
  sync
  umount $root_dev

fi                #end of $sd_partcount -gt 1


if [  $sd_partcount -eq 3 ]
then

  fdisk -o Type -l $user_dev > /tmp/fdisk_out
  a= $(awk '/^Disklabel type: / { print $3 }' /tmp/fdisk_out)
  if [ "$a" == "dos" ]
  then
    echo $user_dev is dos formatted
    dosfsck -a-f-V $user_dev > /dev/nul 2>&1
  else
    echo $user_dev is linux formatted
    e2fsck -fy $user_dev > /dev/null 2>&1
  fi
  # make sure the user filesystem is clean

  # mount the user fs for cleanup
  user_mount=${tmp_path}/user
  mkdir -p $user_mount
  mount $user_dev $user_mount

  # clean up any artifacts from provisioning
  rm -rf $user_mount/root/.bash_history
  rm -rf $user_mount/root/.ansible
  rm -rf $user_mount/root/.ssh
  # pip cache
  rm -rf $user_mount/root/.cache

  rm -rf $user_mount/home/pi/.bash_history
  rm -rf $user_mount/home/pi/.ansible
  rm -rf $user_mount/home/pi/.ssh
  # pip cache
  rm -rf $user_mount/home/pi/.cache

  # empty all of the log files!
  find $user_mount/var/log/ -type f | while read file; do
    echo -n > "$file"
  done

  # defragment (should allow for smaller shrinking)
  echo "defragmenting $user_dev... (this may take a while)"
  e4defrag $user_dev

  # unmount the filesystems preparing for shrinking
  sync
  umount $user_dev

fi          #end of $sd_partcount -eq 3



# clean up the temporary working directory
rm -rf $tmp_path
rm -rf /tmp/temp

if [ $sd_partcount -gt 0 ]
then

  # make sure the filesystem is clean (for sanity)

  a= $(awk '/^Disklabel type: / { print $3 }' /tmp/fdisk_out)
  if [ "$a" == "dos" | $sd_partcount -gt 2 ]
  then
     echo "skipping resize of DOS partiton $root_dev maybe due to partiton 3 -cant be done"
  else
  # shrink as small as possible
  echo "resizing $root_dev filesystem..."
  resize2fs -fpM $root_dev
  fi

fi   #end of if $sd_partcount -gt 0 then;

if [ $sd_partcount -eq 3 ]
then
  # make sure the filesystem is clean (for sanity)
  e2fsck -fy $user_dev > /dev/null 2>&1

  # shrink as small as possible
  echo "resizing $user_dev filesystem..."
  resize2fs -fpM $user_dev
fi

if [ $sd_partcount -gt 0 ]
then
  # get more details about the disk
  sd_block_size=$(cat $sd_sysfs/queue/logical_block_size)
  sd_disk_size=$(cat $sd_sysfs/size)

  # get the partition information
  root_fs_start_sector=$(cat $root_sysfs/start)
  root_fs_sector_count=$(cat $root_sysfs/size)
  root_fs_final_sector=$(( $root_fs_start_sector + $root_fs_sector_count - 1 )) # range is inclusive

  # get the filesystem block count/size
  root_fs_blockcount=$(tune2fs -l $root_dev | awk '/^Block count:/ { print $3 }')
  root_fs_blocksize=$(tune2fs -l $root_dev | awk '/^Block size:/ { print $3 }')

  # adjust the filesystem units to sectors
  root_fs_sector_count=$(( $root_fs_blockcount * $root_fs_blocksize / $sd_block_size ))

  # calculate the new ending sector and resize
  updated_final_sector=$(( $root_fs_start_sector + $root_fs_sector_count - 1 )) # range is inclusive
  updated_sector_count=$(( $updated_final_sector + 1 ))
  root_updated_sector_count=$updated_sector_count
  final_updated_sector_count=$root_updated_sector_count
  # only try to resize the partition if it's actually necessary
  # (parted whines if it's not...)
  if [ $updated_final_sector -lt $root_fs_final_sector ]
  then
    echo "resizing $root_dev partition..."
    parted $sd_devpath unit s resizepart $root_partition_num $updated_final_sector yes
    sync
  fi
fi            # end of if $sd_partcount -gt 1

if [ $sd_partcount -eq 3 ]
then
  # get more details about the disk
  sd_block_size=$(cat $sd_sysfs/queue/logical_block_size)
  sd_disk_size=$(cat $sd_sysfs/size)

  # get the partition information
  user_fs_start_sector=$(cat $user_sysfs/start)
  user_fs_sector_count=$(cat $user_sysfs/size)
  user_fs_final_sector=$(( $user_fs_start_sector + $user_fs_sector_count - 1 )) # range is inclusive

  # get the filesystem block count/size
  user_fs_blockcount=$(tune2fs -l $user_dev | awk '/^Block count:/ { print $3 }')
  user_fs_blocksize=$(tune2fs -l $user_dev | awk '/^Block size:/ { print $3 }')

  # adjust the filesystem units to sectors
  user_fs_sector_count=$(( $user_fs_blockcount * $user_fs_blocksize / $sd_block_size ))

  # calculate the new ending sector and resize
  updated_final_sector=$(( $user_fs_start_sector + $user_fs_sector_count - 1 )) # range is inclusive
  updated_sector_count=$(( $updated_final_sector + 1 ))
  user_updated_sector_count=$updated_sector_count
  final_updated_sector_count=$user_updated_sector_count
  # only try to resize the partition if it's actually necessary
  # (parted whines if it's not...)
  if [ $updated_final_sector -lt $user_fs_final_sector ]; then
    echo "resizing $user_dev partition..."
    parted $sd_devpath unit s resizepart $user_partition_num $updated_final_sector yes
    sync
  fi
fi           #end of if $sd_partcount -eq 3


echo "Ready to copy file to disk.  First check the partitions"
echo "Final sector count is now 1st" $root_updated_sector_count 
echo "final sector count is now 2nd" $user_updated_sector_count
echo "Total count is now" $final_updated_sector_count
echo "block size is " $sd_block_size

# copy out the shrunken image
dd bs=$sd_block_size count=$final_updated_sector_count if=$sd_devpath of=$output_img 
echo "$output_img"

exit 0

