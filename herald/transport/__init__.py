"""Where the ambulance is going and when it gets there: the county's receiving hospitals, the vehicle's position,
road drive times from a local router, a spoken destination matched to the county list, and the one hospital Herald
suggests from the county's own destination rules."""
from .facilities import Facility, facilities
from .routing import OsrmRouter
from .resolver import DestinationResolver
from .selection import DestinationPolicy, Situation
from .service import TransportService

__all__ = ["Facility", "facilities", "OsrmRouter", "DestinationResolver", "DestinationPolicy", "Situation",
           "TransportService"]
