from fastmcp import FastMCP
from .wms import wms_movements, wms_inventory, wms_picking_docs
from .tms import tms_shipments, tms_delivery_events, tms_otif, tms_update_shipment, upload_pdf

mcp = FastMCP("scm-airtable")

mcp.tool()(wms_movements)
mcp.tool()(wms_inventory)
mcp.tool()(wms_picking_docs)
mcp.tool()(tms_shipments)
mcp.tool()(tms_delivery_events)
mcp.tool()(tms_otif)
mcp.tool()(tms_update_shipment)
mcp.tool()(upload_pdf)
