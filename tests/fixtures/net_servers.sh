#!/bin/bash
# Real servers for the other-computers tests: sshd on 127.0.0.1:2222 (passwords) and :2223 (keys only),
# and Samba on 127.0.0.1:445 with a share for alice (Media), a guest share (Public), and Windows' own C$; and on
# :4445 a Samba like Windows (no guests: it asks for a login). "stop" stops them all (by their pid files).
SP="${PIETATO_TEST_WORK:?}"
D=$SP/netsrv
case "$1" in
stop)
  for f in $D/*.pid $D/win/*.pid; do [ -f "$f" ] && kill $(cat "$f") 2>/dev/null; done
  exit 0 ;;
esac
mkdir -p $D
id alice >/dev/null 2>&1 || useradd -m -s /bin/bash alice
echo 'alice:Op3n Sesame!' | chpasswd
mkdir -p /home/alice/Videos /home/alice/Music "/home/alice/My Photos"
printf 'hello from alice\n' > /home/alice/notes.txt
python3 - <<'PY'
from PIL import Image
Image.new("RGB", (64, 48), (200, 40, 40)).save("/home/alice/My Photos/red.jpg")
PY
head -c 300000 /dev/urandom > /home/alice/Videos/clip.mp4
printf 'x' > /home/alice/.secret
chown -R alice:alice /home/alice
mkdir -p /run/sshd
ssh-keygen -A >/dev/null 2>&1
cat > $D/sshd_pw.conf <<CONF
Port 2222
ListenAddress 127.0.0.1
PasswordAuthentication yes
KbdInteractiveAuthentication no
UsePAM yes
PidFile $D/sshd_pw.pid
Subsystem sftp internal-sftp
CONF
cat > $D/sshd_keys.conf <<CONF
Port 2223
ListenAddress 127.0.0.1
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM yes
PidFile $D/sshd_keys.pid
Subsystem sftp internal-sftp
CONF
/usr/sbin/sshd -f $D/sshd_pw.conf
/usr/sbin/sshd -f $D/sshd_keys.conf
mkdir -p $D/media/Films $D/public $D/cdrive
printf 'film\n' > $D/media/Films/movie.mkv
printf 'song\n' > "$D/public/a song.mp3"
chmod -R a+rX $D/media $D/public
chown -R alice $D/media
cat > $D/smb.conf <<CONF
[global]
  workgroup = WORKGROUP
  interfaces = lo
  bind interfaces only = yes
  smb ports = 445
  map to guest = Bad User
  server min protocol = SMB2_02
  pid directory = $D
  lock directory = $D/lock
  state directory = $D/state
  cache directory = $D/cache
  private dir = $D/private
  log file = $D/smb.log
  ncalrpc dir = $D/ncalrpc
  disable spoolss = yes
  load printers = no
[Media]
  path = $D/media
  valid users = alice
  read only = yes
[Public]
  path = $D/public
  guest ok = yes
  read only = yes
[C\$]
  path = $D/cdrive
  valid users = alice
CONF
mkdir -p $D/ncalrpc /run/samba
mkdir -p $D/lock $D/state $D/cache $D/private
(echo 'Op3n Sesame!'; echo 'Op3n Sesame!') | smbpasswd -c $D/smb.conf -s -a alice >/dev/null
smbd -s $D/smb.conf -D
mkdir -p $D/win
sed -e 's/^  smb ports = 445$/  smb ports = 4445/' -e 's/^  map to guest = Bad User$/  map to guest = Never\n  restrict anonymous = 2/' \
    -e "s|^  pid directory = .*|  pid directory = $D/win|" $D/smb.conf > $D/smb_win.conf
smbd -s $D/smb_win.conf -D
sleep 1
echo started
