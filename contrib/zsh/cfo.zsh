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

cfo() {
  emulate -L zsh
  setopt local_options noshwordsplit
  local root target lookup_status
  local -a cmd
  root="${${(%):-%x}:A:h}"
  while [[ "$root" != "/" && ! -f "$root/pyproject.toml" ]]; do
    root="${root:h}"
  done
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
