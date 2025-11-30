import React, { useState } from 'react'
import { clearTokens } from '../auth'
import FileUpload from '../components/FileUpload'
import FileManager from '../components/FileManager'   
import JobCreator from '../components/JobCreator'
import JobList from '../components/JobList'
import JobPreview from '../components/JobPreview'

export default function Dashboard() {
  const [fileId, setFileId] = useState(null)
  const [currentJobId, setCurrentJobId] = useState(null)

  return (
    <div className="app">
      <div className="row" style={{justifyContent:'space-between', marginBottom:12}}>
        <h1>LeafLab</h1>
        <button onClick={()=>{ clearTokens(); location.href='/'; }}>Logout</button>
      </div>

      <FileUpload onUploaded={(id)=>{ setFileId(id); }} />

      <FileManager onSelectFile={(id)=> setFileId(id)} />

      <div className="card">
        <div className="row">
          <label>Current file_id</label>
          <input readOnly value={fileId || ''} style={{width:180}} />
        </div>
      </div>

      <JobCreator fileId={fileId} onCreated={(jid)=> setCurrentJobId(jid)} />
      <JobList onSelect={(jid)=> setCurrentJobId(jid)} />
      <JobPreview jobId={currentJobId} />
    </div>
  )
}
