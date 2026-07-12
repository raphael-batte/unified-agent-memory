#!/usr/bin/env bash
# Shared local plugin + skill symlink helpers (sourced by install-local.sh, skills-status.sh).

plugin_local_target() {
  local plugin_name="${1:-agent-memory}"
  echo "${CURSOR_PLUGINS_LOCAL:-$HOME/.cursor/plugins/local}/$plugin_name"
}

cursor_skills_dir() {
  echo "${CURSOR_SKILLS:-$HOME/.cursor/skills}"
}

cursor_rules_dir() {
  echo "${CURSOR_RULES:-$HOME/.cursor/rules}"
}

global_routing_rule_name() {
  echo "agent-memory-routing.mdc"
}

link_global_routing_rules() {
  local src="$1"
  local rule_src cursor_rules rule_dest
  rule_src="$src/rules/$(global_routing_rule_name)"
  if [[ ! -f "$rule_src" ]]; then
    echo "Error: missing global routing rule: $rule_src" >&2
    return 1
  fi
  cursor_rules="$(cursor_rules_dir)"
  mkdir -p "$cursor_rules"
  rule_dest="$cursor_rules/$(global_routing_rule_name)"
  if [[ -e "$rule_dest" || -L "$rule_dest" ]]; then
    rm -f "$rule_dest"
  fi
  ln -sfn "$rule_src" "$rule_dest"
  echo "  rule:  $rule_dest → $rule_src"
}

link_local_plugin() {
  local src="$1"
  local plugin_name="${2:-agent-memory}"
  local target
  target="$(plugin_local_target "$plugin_name")"
  mkdir -p "$(dirname "$target")"
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf "$target"
  fi
  ln -sfn "$src" "$target"
  printf '%s' "$target"
}

link_bundle_skills() {
  local src="$1"
  local skills_dir="$src/skills"
  local cursor_skills
  cursor_skills="$(cursor_skills_dir)"

  if [[ ! -d "$skills_dir" ]]; then
    echo "Error: missing bundle skills dir: $skills_dir" >&2
    return 1
  fi

  mkdir -p "$cursor_skills"

  local entry name dest skill_dir
  for entry in "$cursor_skills"/*; do
    [[ -L "$entry" ]] || continue
    [[ -e "$entry" ]] && continue
    rm -f "$entry"
    echo "  removed broken skill symlink: $(basename "$entry")"
  done

  local linked=0
  for skill_dir in "$skills_dir"/*; do
    [[ -d "$skill_dir" && -f "$skill_dir/SKILL.md" ]] || continue
    name="$(basename "$skill_dir")"
    dest="$cursor_skills/$name"
    if [[ -e "$dest" || -L "$dest" ]]; then
      rm -rf "$dest"
    fi
    ln -sfn "$skill_dir" "$dest"
    echo "  skill: $dest → $skill_dir"
    linked=$((linked + 1))
  done

  if [[ "$linked" -eq 0 ]]; then
    echo "Error: no SKILL.md found under $skills_dir" >&2
    return 1
  fi
  return 0
}

verify_plugin_install() {
  local src="$1"
  local plugin_name="${2:-agent-memory}"
  local target cursor_skills name skill_dir
  target="$(plugin_local_target "$plugin_name")"
  cursor_skills="$(cursor_skills_dir)"

  if [[ ! -L "$target" && ! -d "$target" ]]; then
    echo "plugin missing: $target" >&2
    return 1
  fi
  if [[ ! -f "$target/.cursor-plugin/plugin.json" ]]; then
    echo "plugin bundle invalid: $target/.cursor-plugin/plugin.json" >&2
    return 1
  fi
  if [[ ! -f "$target/skills/agent-memory/SKILL.md" ]]; then
    echo "entry skill missing: $target/skills/agent-memory/SKILL.md" >&2
    return 1
  fi

  name="agent-memory"
  skill_dir="$cursor_skills/$name"
  if [[ ! -f "$skill_dir/SKILL.md" ]]; then
    echo "cursor skill missing: $skill_dir/SKILL.md" >&2
    return 1
  fi
  local resolved_skill resolved_bundle
  resolved_skill="$(cd "$skill_dir" 2>/dev/null && pwd -P || true)"
  resolved_bundle="$(cd "$src/skills/agent-memory" && pwd -P)"
  if [[ "$resolved_skill" != "$resolved_bundle" ]]; then
    echo "cursor skill not linked to bundle: $skill_dir (got $resolved_skill)" >&2
    return 1
  fi

  local rule_dest rule_src resolved_rule expected_rule
  rule_src="$src/rules/$(global_routing_rule_name)"
  rule_dest="$(cursor_rules_dir)/$(global_routing_rule_name)"
  if [[ ! -f "$rule_src" ]]; then
    echo "bundle routing rule missing: $rule_src" >&2
    return 1
  fi
  if [[ ! -L "$rule_dest" && ! -f "$rule_dest" ]]; then
    echo "global routing rule missing: $rule_dest (re-run install-local.sh)" >&2
    return 1
  fi
  resolved_rule="$(python3 -c "import os; print(os.path.realpath('${rule_dest}'))" 2>/dev/null || true)"
  expected_rule="$(python3 -c "import os; print(os.path.realpath('${rule_src}'))" 2>/dev/null || true)"
  if [[ -n "$resolved_rule" && -n "$expected_rule" && "$resolved_rule" != "$expected_rule" ]]; then
    echo "global routing rule not linked to bundle: $rule_dest" >&2
    return 1
  fi
  return 0
}
