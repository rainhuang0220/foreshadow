# cfo — change to a checkout registered with Foreshadow.
#
# Optional. Add this line to ~/.zshrc yourself; nothing sources it automatically:
#
#   source "$HOME/Desktop/Foreshadow/contrib/zsh/cfo.zsh"
#
# Then, from any directory:
#
#   cfo ripwire
#   cfo moonbitlang/core
#
# The function uses this checkout's uv environment, or .venv/bin/foreshadow when
# uv is not on PATH. foreshadow does not need to be installed globally.
# A failed lookup prints the error and leaves the current directory unchanged.

typeset -g _FORESHADOW_CFO_ROOT="${${(%):-%x}:A:h}"
while [[ "$_FORESHADOW_CFO_ROOT" != "/" && ! -f "$_FORESHADOW_CFO_ROOT/pyproject.toml" ]]; do
  _FORESHADOW_CFO_ROOT="${_FORESHADOW_CFO_ROOT:h}"
done

cfo() {
  emulate -L zsh
  setopt local_options noshwordsplit
  local root target lookup_status
  local -a cmd
  root="$_FORESHADOW_CFO_ROOT"
  if [[ ! -f "$root/pyproject.toml" ]]; then
    print -u2 -- "cfo: cannot find the Foreshadow checkout"
    return 1
  fi
  if (( $+commands[uv] )); then
    cmd=(uv run --project "$root" foreshadow)
  elif [[ -x "$root/.venv/bin/foreshadow" ]]; then
    cmd=("$root/.venv/bin/foreshadow")
  else
    print -u2 -- "cfo: uv or $root/.venv/bin/foreshadow is required"
    return 127
  fi
  target="$("${cmd[@]}" repos path "$@")"
  lookup_status=$?
  if (( lookup_status != 0 )); then
    return lookup_status
  fi
  if [[ -z "$target" || "$target" == *$'\n'* ]]; then
    print -u2 -- "cfo: expected one directory path"
    return 1
  fi
  cd -- "$target"
}
