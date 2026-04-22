#!/bin/bash
#
# build_installer.sh — generates the self-extracting condor_voz installer
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_DIR="$SCRIPT_DIR"
OUT="$ROOT_DIR/condor_voz"
REMOTE_DEST="cadrete@155.210.153.33:public_html"
# REMOTE_DEST="cadrete@signal24:/home/cadrete/Dropbox/shared/condor"

# Collect all scripts into a tar.gz payload
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

FOUND_FILES=0
for f in "$PACKAGE_DIR"/*; do
	[[ -f "$f" ]] || continue
	case "$(basename "$f")" in
		build_installer.sh|condor_cpu|condor_nice|condor_local|condor_cpu_local|condor_nice_local)
			continue
			;;
	esac
	cp "$f" "$TMPDIR/$(basename "$f")"
	chmod +x "$TMPDIR/$(basename "$f")"
	FOUND_FILES=1
done

if [[ "$FOUND_FILES" -eq 0 ]]; then
	echo "No package files found in $PACKAGE_DIR" >&2
	exit 1
fi

# Build list of basenames for the tar
NAMES=()
for f in "$TMPDIR"/*; do
	[[ -f "$f" ]] || continue
	NAMES+=("$(basename "$f")")
done

# Create the tar.gz payload
PAYLOAD="$TMPDIR/payload.tar.gz"
tar -czf "$PAYLOAD" -C "$TMPDIR" "${NAMES[@]}"

# Build the installer by writing it in parts (avoids sed on huge base64)
cat > "$OUT" << 'PART1'
#!/bin/bash
# ============================================================================
#  condor_voz — interactive installer for vvtk_condor tools
#
#  Install:  curl -fsSL <URL>/condor_voz | bash
#        or: bash condor_voz
# ============================================================================
{
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
read -rp "  Install directory [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR < /dev/tty
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
PART1

# Part 2: the payload variable (inlined directly, no sed)
B64=$(base64 -w0 "$PAYLOAD")
echo "PAYLOAD_B64='${B64}'" >> "$OUT"

echo "INSTALL_FILES=(" >> "$OUT"
for name in "${NAMES[@]}"; do
	printf "'%s'\n" "$name" >> "$OUT"
done
echo ")" >> "$OUT"

# Part 3: rest of the installer
cat >> "$OUT" << 'PART3'
echo "$PAYLOAD_B64" | base64 -d | tar -xzf - -C "$INSTALL_DIR"
for installed_file in "${INSTALL_FILES[@]}"; do
	chmod +x "$INSTALL_DIR/$installed_file"
done
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
# 4. Offer to add convenience aliases to .bashrc
# ---------------------------------------------------------------
VOZ_ALIASES=(
	"alias condor_cpu='condor --nogpu'"
	"alias condor_nice='condor --nice'"
	"alias condor_local='condor --local'"
	"alias condor_cpu_local='condor --nogpu --local'"
	"alias condor_nice_local='condor --nice --local'"
)

MISSING_VOZ_ALIASES=()
for alias_line in "${VOZ_ALIASES[@]}"; do
	if [[ ! -f "$BASHRC" ]] || ! grep -qF "$alias_line" "$BASHRC"; then
		MISSING_VOZ_ALIASES+=("$alias_line")
	fi
done

if [[ ${#MISSING_VOZ_ALIASES[@]} -gt 0 ]]; then
	echo -e "${CYAN}Optional condor command aliases can be added to $BASHRC.${RESET}"
	echo "  If you answer yes, these lines will be appended:"
	for alias_line in "${MISSING_VOZ_ALIASES[@]}"; do
		echo "    $alias_line"
	done
	read -rp "  Add the missing alias lines to $BASHRC? [Y/n]: " ADD_ALIASES < /dev/tty
	ADD_ALIASES="${ADD_ALIASES:-Y}"
	if [[ "$ADD_ALIASES" =~ ^[Yy] ]]; then
		echo "" >> "$BASHRC"
		echo "# condor_voz aliases" >> "$BASHRC"
		for alias_line in "${MISSING_VOZ_ALIASES[@]}"; do
			echo "$alias_line" >> "$BASHRC"
		done
		echo -e "  -> ${GREEN}Added aliases to $BASHRC${RESET}"
	else
		echo -e "  -> ${YELLOW}Skipped.${RESET}"
	fi
else
	echo -e "${GREEN}condor command aliases already configured in $BASHRC.${RESET}"
fi
echo ""

# ---------------------------------------------------------------
# 5. Offer to add HTCondor system paths to .bashrc
# ---------------------------------------------------------------
CONDOR_BIN_DIR='/usr/local/condor/x86_64/bin'
CONDOR_LIB_DIR='/usr/local/condor/x86_64/lib'
CONDOR_CONFIG_FILE='/usr/local/condor/x86_64/etc/condor_config'
CONDOR_PATH_LINE='export PATH=/usr/local/condor/x86_64/bin:$PATH'
CONDOR_LIB_LINE='export LD_LIBRARY_PATH=/usr/local/condor/x86_64/lib:$LD_LIBRARY_PATH'
CONDOR_CONFIG_LINE='export CONDOR_CONFIG=/usr/local/condor/x86_64/etc/condor_config'

path_has_entry() {
	printf '%s' "$1" | tr ':' '\n' | sed 's:/*$::' | grep -qx "$2"
}

NEED_CONDOR_SETUP=false
NEED_CONDOR_BIN=false
NEED_CONDOR_LIB=false
NEED_CONDOR_CONFIG=false

if [[ -f "$BASHRC" ]]; then
	grep -qF "$CONDOR_BIN_DIR" "$BASHRC" || NEED_CONDOR_BIN=true
	grep -qF "$CONDOR_LIB_DIR" "$BASHRC" || NEED_CONDOR_LIB=true
	grep -qF "$CONDOR_CONFIG_FILE" "$BASHRC" || NEED_CONDOR_CONFIG=true
else
	NEED_CONDOR_BIN=true
	NEED_CONDOR_LIB=true
	NEED_CONDOR_CONFIG=true
fi

if [[ "$NEED_CONDOR_BIN" == true || "$NEED_CONDOR_LIB" == true || "$NEED_CONDOR_CONFIG" == true ]]; then
	NEED_CONDOR_SETUP=true
fi

if [[ "$NEED_CONDOR_SETUP" == true ]]; then
	echo -e "${CYAN}Missing HTCondor configuration detected in $BASHRC.${RESET}"
	echo "  If you answer yes, these lines will be appended:"
	[[ "$NEED_CONDOR_BIN" == true ]] && echo "    $CONDOR_PATH_LINE"
	[[ "$NEED_CONDOR_LIB" == true ]] && echo "    $CONDOR_LIB_LINE"
	[[ "$NEED_CONDOR_CONFIG" == true ]] && echo "    $CONDOR_CONFIG_LINE"
	read -rp "  Add the missing lines to $BASHRC? [Y/n]: " ADD_CONDOR < /dev/tty
	ADD_CONDOR="${ADD_CONDOR:-Y}"
	if [[ "$ADD_CONDOR" =~ ^[Yy] ]]; then
		echo "" >> "$BASHRC"
		echo "# HTCondor system paths" >> "$BASHRC"
		[[ "$NEED_CONDOR_BIN" == true ]] && echo "$CONDOR_PATH_LINE" >> "$BASHRC"
		[[ "$NEED_CONDOR_LIB" == true ]] && echo "$CONDOR_LIB_LINE" >> "$BASHRC"
		[[ "$NEED_CONDOR_CONFIG" == true ]] && echo "$CONDOR_CONFIG_LINE" >> "$BASHRC"
		echo -e "  -> ${GREEN}Added to $BASHRC${RESET}"
	else
		echo -e "  -> ${YELLOW}Skipped.${RESET}"
	fi
else
	echo -e "${GREEN}HTCondor environment already configured in $BASHRC.${RESET}"
fi
echo ""

# ---------------------------------------------------------------
# 6. Summary
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

exit 0
}
PART3

chmod +x "$OUT"
echo "Built installer: $OUT ($(du -h "$OUT" | cut -f1))"
scp "$OUT" "$REMOTE_DEST"
rm -f "$OUT"
echo "Uploaded installer $OUT to $REMOTE_DEST"