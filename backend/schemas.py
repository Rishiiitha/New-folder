from pydantic import BaseModel
from typing import Optional

# ... (Your existing StudentRewardData class) ...

class StudentAcademicData(BaseModel):
    roll_no: str
    name: Optional[str] = None
    email: Optional[str] = None
    attendance: Optional[float] = None
    cgpa: Optional[float] = None
    fees_pending: Optional[float] = None

    class Config:
        from_attributes = True