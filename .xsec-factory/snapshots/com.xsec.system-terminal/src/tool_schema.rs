use rmcp::model::Tool;
use serde_json::{json, Map, Value};

const TOOLS: &[(&str, &str)] = &[
    (
        "terminal_profiles",
        "Return the Host platform and available shell profiles.",
    ),
    (
        "terminal_open",
        "Create a session-shared PTY and add it to the terminal list in the user bottom dock.",
    ),
    (
        "terminal_list",
        "List the system terminals of the current session, including ended ones (state exited or terminated) that have not yet been evicted.",
    ),
    (
        "terminal_read",
        "Read non-consuming UTF-8 terminal output from an independent cursor; works on ended terminals until they are evicted.",
    ),
    (
        "terminal_write",
        "Write raw terminal input, including control characters, without retries; fails on an ended terminal.",
    ),
    (
        "terminal_resize",
        "Resize the PTY.",
    ),
    (
        "terminal_reveal",
        "Reveal the terminal panel with an existing session terminal in the user bottom dock.",
    ),
    (
        "terminal_close",
        "Explicitly terminate a terminal process and return its final state; the ended terminal stays listed and readable until evicted.",
    ),
];

pub fn tool_descriptors() -> Vec<Tool> {
    TOOLS
        .iter()
        .map(|(name, description)| Tool::new(*name, *description, schema(name)))
        .collect()
}

pub fn host_method(tool: &str) -> Result<&'static str, String> {
    match tool {
        "terminal_profiles" => Ok("xsec.terminal.profiles"),
        "terminal_open" => Ok("xsec.terminal.open"),
        "terminal_list" => Ok("xsec.terminal.list"),
        "terminal_read" => Ok("xsec.terminal.read"),
        "terminal_write" => Ok("xsec.terminal.write"),
        "terminal_resize" => Ok("xsec.terminal.resize"),
        "terminal_reveal" => Ok("xsec.terminal.reveal"),
        "terminal_close" => Ok("xsec.terminal.close"),
        _ => Err(format!("unknown system-terminal MCP tool: {tool}")),
    }
}

fn schema(tool: &str) -> Map<String, Value> {
    let value = match tool {
        "terminal_profiles" | "terminal_list" => {
            json!({ "type": "object", "additionalProperties": false })
        }
        "terminal_open" => json!({
            "type": "object", "additionalProperties": false,
            "properties": {
                "title": { "type": "string", "maxLength": 256 },
                "cwd": { "type": "string", "maxLength": 4096 },
                "profile_id": { "type": "string", "maxLength": 128 },
                "cols": { "type": "integer", "minimum": 20, "maximum": 400 },
                "rows": { "type": "integer", "minimum": 2, "maximum": 200 }
            }
        }),
        "terminal_read" => json!({
            "type": "object", "additionalProperties": false, "required": ["terminal_id"],
            "properties": {
                "terminal_id": { "type": "string", "minLength": 1, "maxLength": 128 },
                "cursor": { "type": "integer", "minimum": 0 },
                "max_bytes": { "type": "integer", "minimum": 1, "maximum": 65536 },
                "wait_ms": { "type": "integer", "minimum": 0, "maximum": 5000 }
            }
        }),
        "terminal_write" => json!({
            "type": "object", "additionalProperties": false, "required": ["terminal_id", "data"],
            "properties": {
                "terminal_id": { "type": "string", "minLength": 1, "maxLength": 128 },
                "data": { "type": "string", "minLength": 1, "maxLength": 65536 }
            }
        }),
        "terminal_resize" => json!({
            "type": "object", "additionalProperties": false, "required": ["terminal_id", "cols", "rows"],
            "properties": {
                "terminal_id": { "type": "string", "minLength": 1, "maxLength": 128 },
                "cols": { "type": "integer", "minimum": 20, "maximum": 400 },
                "rows": { "type": "integer", "minimum": 2, "maximum": 200 }
            }
        }),
        "terminal_reveal" | "terminal_close" => json!({
            "type": "object", "additionalProperties": false, "required": ["terminal_id"],
            "properties": { "terminal_id": { "type": "string", "minLength": 1, "maxLength": 128 } }
        }),
        _ => unreachable!("tool descriptor table is fixed"),
    };
    value
        .as_object()
        .cloned()
        .expect("system terminal schemas are objects")
}

#[cfg(test)]
mod tests {
    use super::{host_method, tool_descriptors};

    #[test]
    fn exposes_the_eight_session_terminal_tools() {
        let names = tool_descriptors()
            .into_iter()
            .map(|tool| tool.name.to_string())
            .collect::<Vec<_>>();
        assert_eq!(
            names,
            vec![
                "terminal_profiles",
                "terminal_open",
                "terminal_list",
                "terminal_read",
                "terminal_write",
                "terminal_resize",
                "terminal_reveal",
                "terminal_close",
            ]
        );
        assert_eq!(host_method("terminal_read").unwrap(), "xsec.terminal.read");
        assert!(host_method("terminal_control_acquire").is_err());
    }

    #[test]
    fn no_tool_takes_a_control_or_takeover_argument() {
        for tool in tool_descriptors() {
            let schema = serde_json::Value::Object((*tool.input_schema).clone());
            let properties = schema["properties"].as_object();
            for argument in ["control", "takeover"] {
                assert!(
                    properties.map_or(true, |p| !p.contains_key(argument)),
                    "{} still has a {argument} argument",
                    tool.name
                );
            }
            assert!(!tool.name.contains("control"), "{} is a control tool", tool.name);
        }
    }
}
