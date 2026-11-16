from app.db import SessionLocal
from app.models import ShopOrder
from app.supplier import KhmerTopUp, SupplierError

supplier = KhmerTopUp()

def approve_order(order_id: int):
    db = SessionLocal()
    try:
        order = db.get(ShopOrder, order_id)
        if not order:
            raise ValueError("Order not found")
        if order.status != "payment_submitted":
            raise ValueError(f"Cannot approve order in status: {order.status}")
        # Use the persistent order_ref as idempotency key; retrying cannot double-charge.
        result = supplier.create_order(
            order.package_id, order.player_id, order.server_id, order.order_ref
        )
        order.supplier_order_code = result.get("order_code")
        order.status = result.get("status", "processing")
        db.commit()
        return order.telegram_id, order.order_ref, order.status, order.supplier_order_code
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def refresh_processing_orders():
    db = SessionLocal()
    changed = []
    try:
        orders = db.query(ShopOrder).filter(
            ShopOrder.status.in_(["processing", "pending", "accepted"])
        ).all()
        for order in orders:
            if not order.supplier_order_code:
                continue
            try:
                result = supplier.order_status(order.supplier_order_code)
                new_status = result.get("status", order.status)
                if new_status in ("completed", "refunded"):
                    order.status = new_status
                    changed.append((order.telegram_id, order.order_ref, new_status, order.supplier_order_code))
            except SupplierError:
                continue
        db.commit()
    finally:
        db.close()
    return changed