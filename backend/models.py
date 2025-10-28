# In models.py

from sqlalchemy import Column, String, NUMERIC
from .database import Base

# ... (Your existing StudentRewards class) ...

class StudentAcademics(Base):
    __tablename__ = "student_academics"

    roll_no = Column(String, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True) # Student's email
    attendance = Column(NUMERIC(5, 2))
    cgpa = Column(NUMERIC(4, 2))
    fees_pending = Column(NUMERIC(10, 2))