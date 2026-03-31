// Stub: this file was not included in the leaked source

export const DEFAULT_UPLOAD_CONCURRENCY = 5
export const FILE_COUNT_LIMIT = 100
export const OUTPUTS_SUBDIR = 'outputs'

export interface PersistedFile {
  path: string
  size: number
}

export interface FailedPersistence {
  path: string
  error: string
}

export interface FilesPersistedEventData {
  files: PersistedFile[]
  failed: FailedPersistence[]
}

export type TurnStartTime = number
