mod host;
mod server;
mod tool_schema;

use anyhow::{Context, Result};
use rmcp::ServiceExt;

use crate::host::HostClient;
use crate::server::SystemTerminalServer;

const HOST_RPC_ENDPOINT_ENV: &str = "XSEC_PLUGIN_HOST_RPC_ENDPOINT";

/// The sidecar intentionally has no standalone mode: exposing a system shell
/// without a Desktop session lease would violate the plugin's trust boundary.
pub async fn run_stdio() -> Result<()> {
    let endpoint = std::env::var(HOST_RPC_ENDPOINT_ENV)
        .context("system-terminal MCP requires XSEC_PLUGIN_HOST_RPC_ENDPOINT")?;
    let client = HostClient::new(endpoint)?;
    eprintln!("system_terminal_mcp.started");
    let running = SystemTerminalServer::new(client)
        .serve(rmcp::transport::stdio())
        .await?;
    running.waiting().await?;
    Ok(())
}
