/**
 * Hand-written mirrors of the backend's Pydantic schemas.
 *
 * Temporary: Issue 12 replaces this file with a client generated from
 * `/api/v1/openapi.json`, which is the contract source (research §595). Until
 * then these are duplicated by hand and can drift — which is exactly why the
 * generated client is a scheduled issue rather than a nice-to-have.
 */

export interface UserPublic {
  id: string
  email: string
}

export interface SessionPublic {
  user: UserPublic
  active_organization_id: string | null
}

export interface OrganizationPublic {
  id: string
  name: string
}

export interface ApiFieldError {
  field: string
  message: string
}

/** The single error envelope every 401/403/404/409/422 uses. */
export interface ApiErrorResponse {
  error: {
    code: string
    message: string
    fields: ApiFieldError[] | null
  }
}
