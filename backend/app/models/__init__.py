"""Import all models so they register on Base.metadata."""
from app.models.audit import AuditLog
from app.models.carrier import Carrier
from app.models.catalog import Commodity, GradeSpec, Variety
from app.models.finance import LedgerEntry, Payment, Payout, Refund
from app.models.location import District, Mandal, State
from app.models.marketplace import (
    RFQ,
    Listing,
    ListingMedia,
    Offer,
    OfferVersion,
)
from app.models.order import (
    Inspection,
    Lot,
    LotEvent,
    Order,
    OrderLine,
    OrderStatusEvent,
    Package,
    Shipment,
    ShipmentEvent,
)
from app.models.prices import MarketPrice
from app.models.pricing import PricingRule
from app.models.review import Review
from app.models.support import (
    ConsentRecord,
    Dispute,
    MediaObject,
    Notification,
    QualityCase,
    SupportTicket,
)
from app.models.user import (
    AgentProfile,
    BuyerProfile,
    FarmerProfile,
    Organisation,
    User,
)

__all__ = [
    "AuditLog",
    "Carrier",
    "Commodity",
    "GradeSpec",
    "Variety",
    "LedgerEntry",
    "Payment",
    "Payout",
    "Refund",
    "District",
    "Mandal",
    "State",
    "RFQ",
    "Listing",
    "ListingMedia",
    "Offer",
    "OfferVersion",
    "Inspection",
    "Lot",
    "LotEvent",
    "Order",
    "OrderLine",
    "OrderStatusEvent",
    "Package",
    "Shipment",
    "ShipmentEvent",
    "PricingRule",
    "Review",
    "AgentProfile",
    "BuyerProfile",
    "FarmerProfile",
    "Organisation",
    "User",
    "MarketPrice",
    "SupportTicket",
    "Dispute",
    "ConsentRecord",
    "Notification",
    "MediaObject",
    "QualityCase",
]
