class UserIsExist(Exception):
    def __init__(self, message:str):
        self.message = message
        super().__init__(self.message)

class UserNotFound(Exception):
    def __init__(self, message:str):
        self.message = message
        super().__init__(self.message)

class UserInvalidPassword(Exception):
    def __init__(self, message:str):
        self.message = message
        super().__init__(self.message)

class InvalidAuthentication(Exception):
    def __init__(self, message:str = 'Invalid Authentication'):
        self.message = message
        super().__init__(self.message)

class TokenExpired(Exception):
    def __init__(self, message:str = 'Token has expired'):
        self.message = message
        super().__init__(self.message)