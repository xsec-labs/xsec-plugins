use rmcp::handler::server::ServerHandler;
use rmcp::model::{
    CallToolRequestParams, CallToolResult, ContentBlock, Implementation, ListToolsResult,
    PaginatedRequestParams, ServerCapabilities, ServerInfo, Tool,
};
use rmcp::service::{RequestContext, RoleServer};
use serde_json::Value;

use crate::host::HostClient;
use crate::tool_schema::{host_method, tool_descriptors};

const CONTEXT_HANDLE_META_KEY: &str = "com.xsec.desktop/contextHandle";
const SERVER_NAME: &str = "system-terminal-mcp";

pub struct SystemTerminalServer {
    client: HostClient,
}

impl SystemTerminalServer {
    pub fn new(client: HostClient) -> Self {
        Self { client }
    }

    async fn execute(
        &self,
        request: CallToolRequestParams,
        context: &RequestContext<RoleServer>,
    ) -> Result<Value, String> {
        let tool = request.name.to_string();
        let handle = context_handle(context)
            .ok_or_else(|| "system-terminal MCP requires a context handle".to_string())?;
        self.client
            .context(handle, &tool)
            .await
            .map_err(|error| error.to_string())?;
        let params = Value::Object(request.arguments.unwrap_or_default());
        self.client
            .call(handle, host_method(&tool)?, params)
            .await
            .map_err(|error| error.to_string())
    }
}

impl ServerHandler for SystemTerminalServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::new(SERVER_NAME, env!("CARGO_PKG_VERSION")))
    }

    async fn list_tools(
        &self,
        _request: Option<PaginatedRequestParams>,
        _context: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, rmcp::model::ErrorData> {
        Ok(ListToolsResult::with_all_items(tool_descriptors()))
    }

    async fn call_tool(
        &self,
        request: CallToolRequestParams,
        context: RequestContext<RoleServer>,
    ) -> Result<CallToolResult, rmcp::model::ErrorData> {
        match self.execute(request, &context).await {
            Ok(payload) => tool_result(payload),
            Err(error) => Ok(tool_error(error)),
        }
    }

    fn get_tool(&self, name: &str) -> Option<Tool> {
        tool_descriptors()
            .into_iter()
            .find(|tool| tool.name == name)
    }
}

fn context_handle(context: &RequestContext<RoleServer>) -> Option<&str> {
    context
        .meta
        .0
        .get(CONTEXT_HANDLE_META_KEY)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
}

fn tool_result(payload: Value) -> Result<CallToolResult, rmcp::model::ErrorData> {
    let content = ContentBlock::json(payload).map_err(|error| {
        rmcp::model::ErrorData::internal_error(
            format!("serialize system-terminal MCP response: {error}"),
            None,
        )
    })?;
    Ok(CallToolResult::success(vec![content]))
}

fn tool_error(message: String) -> CallToolResult {
    CallToolResult::error(vec![ContentBlock::text(
        serde_json::json!({ "error": message }).to_string(),
    )])
}
