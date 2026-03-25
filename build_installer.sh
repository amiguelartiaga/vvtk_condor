#!/bin/bash
#
# build_installer.sh — generates the self-extracting condor_voz installer
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/src"
OUT="$SCRIPT_DIR/condor_voz"
REMOTE_DEST="cadrete@155.210.153.33:public_html"
# REMOTE_DEST="cadrete@signal24:/home/cadrete/Dropbox/shared/condor"

# Collect all scripts into a tar.gz payload
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Copy all scripts flat into staging dir
for f in "$SRC/voz/"*; do
    [[ -f "$f" ]] || continue
    cp "$f" "$TMPDIR/$(basename "$f")"
    chmod +x "$TMPDIR/$(basename "$f")"
done

# Build list of basenames for the tar
NAMES=()
for f in "$TMPDIR"/*; do
    [[ -f "$f" ]] || continue
    NAMES+=("$(basename "$f")")
done

# Create the tar.gz payload
PAYLOAD="$TMPDIR/payload.tar.gz"
tar -czf "$PAYLOAD" -C "$TMPDIR" "${NAMES[@]}"

# Write the installer header
cat > "$OUT" << 'INSTALLER_HEADER'
#!/bin/bash
# ============================================================================
#  condor_voz — interactive installer for vvtk_condor tools
#
#  Install:  curl -fsSL <URL>/condor_voz | bash
#        or: bash condor_voz
# ============================================================================
set -e

BOLD='\e[1m'
GREEN='\e[1;32m'
YELLOW='\e[1;33m'
CYAN='\e[1;36m'
RESET='\e[0m'

echo -e "${BOLD}======================================${RESET}"
echo -e "${GREEN}  condor_voz installer${RESET}"
echo -e "${BOLD}======================================${RESET}"
echo ""

# ---------------------------------------------------------------
# 1. Installation directory
# ---------------------------------------------------------------
DEFAULT_INSTALL_DIR="$HOME/.local/bin"
echo -e "${CYAN}Where should the scripts be installed?${RESET}"
read -rp "  Install directory [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

# Expand ~ if the user typed it
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

mkdir -p "$INSTALL_DIR"
echo -e "  -> ${GREEN}$INSTALL_DIR${RESET}"
echo ""

# ---------------------------------------------------------------
# 2. Extract payload (base64-encoded tar.gz)
# ---------------------------------------------------------------
echo "Extracting scripts..."
echo "__PAYLOAD_BASE64__" | base64 -d | tar -xzf - -C "$INSTALL_DIR"
chmod +x "$INSTALL_DIR"/*
echo -e "  -> ${GREEN}Done${RESET}"
echo ""

# ---------------------------------------------------------------
# 3. Offer to add INSTALL_DIR to PATH in .bashrc
# ---------------------------------------------------------------
BASHRC="$HOME/.bashrc"
PATH_LINE="export PATH=\"\$PATH:$INSTALL_DIR\""

if echo "$PATH" | tr ':' '\n' | grep -qx "$INSTALL_DIR"; then
    echo -e "${GREEN}$INSTALL_DIR is already in your PATH.${RESET}"
elif [[ -f "$BASHRC" ]] && grep -qF "$INSTALL_DIR" "$BASHRC"; then
    echo -e "${GREEN}$INSTALL_DIR is already referenced in $BASHRC.${RESET}"
else
    echo -e "${CYAN}Add $INSTALL_DIR to PATH in $BASHRC?${RESET}"
    read -rp "  [Y/n]: " ADD_PATH < /dev/tty
    ADD_PATH="${ADD_PATH:-Y}"
    if [[ "$ADD_PATH" =~ ^[Yy] ]]; then
        echo "" >> "$BASHRC"
        echo "# condor_voz tools" >> "$BASHRC"
        echo "$PATH_LINE" >> "$BASHRC"
        echo -e "  -> ${GREEN}Added to $BASHRC${RESET}"
    else
        echo -e "  -> ${YELLOW}Skipped. Add manually:${RESET}  $PATH_LINE"
    fi
fi
echo ""

# ---------------------------------------------------------------
# 4. Offer to add HTCondor system paths to .bashrc
# ---------------------------------------------------------------
CONDOR_PATH_LINE='export PATH="$PATH:/usr/local/condor/x86_64/bin/"'
CONDOR_SOURCE_LINE='source /usr/local/condor/condor.sh'

NEED_CONDOR_SETUP=false
if [[ -f "$BASHRC" ]]; then
    grep -qF '/usr/local/condor' "$BASHRC" || NEED_CONDOR_SETUP=true
else
    NEED_CONDOR_SETUP=true
fi

if [[ "$NEED_CONDOR_SETUP" == true ]]; then
    echo -e "${CYAN}Add HTCondor system paths to $BASHRC?${RESET}"
    echo "  This will add:"
    echo "    $CONDOR_PATH_LINE"
    echo "    $CONDOR_SOURCE_LINE"
    read -rp "  [Y/n]: " ADD_CONDOR < /dev/tty
    ADD_CONDOR="${ADD_CONDOR:-Y}"
    if [[ "$ADD_CONDOR" =~ ^[Yy] ]]; then
        echo "" >> "$BASHRC"
        echo "# HTCondor system paths" >> "$BASHRC"
        echo "$CONDOR_PATH_LINE" >> "$BASHRC"
        echo "$CONDOR_SOURCE_LINE" >> "$BASHRC"
        echo -e "  -> ${GREEN}Added to $BASHRC${RESET}"
    else
        echo -e "  -> ${YELLOW}Skipped.${RESET}"
    fi
else
    echo -e "${GREEN}HTCondor paths already configured in $BASHRC.${RESET}"
fi
echo ""

# ---------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------
echo -e "${BOLD}======================================${RESET}"
echo -e "${GREEN}  Installation complete!${RESET}"
echo -e "${BOLD}======================================${RESET}"
echo ""
echo "  Installed scripts:"
ls -1 "$INSTALL_DIR"/condor* "$INSTALL_DIR"/_condor_submit.sh 2>/dev/null | while read -r f; do
    echo "    $(basename "$f")"
done
echo ""
echo -e "  Run ${CYAN}condor --help${RESET} to get started."
echo -e "  You may need to ${YELLOW}source ~/.bashrc${RESET} or open a new terminal."
echo ""
INSTALLER_HEADER

# Replace the placeholder with the actual base64-encoded payload
B64=$(base64 -w0 "$PAYLOAD")
sed -i "s|__PAYLOAD_BASE64__|${B64}|" "$OUT"

chmod +x "$OUT"
echo "Built installer: $OUT ($(du -h "$OUT" | cut -f1))"
scp "$OUT" "$REMOTE_DEST"
echo "Uploaded installer to $REMOTE_DEST"
