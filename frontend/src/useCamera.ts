import { useCallback, useEffect, useRef, useState } from 'react'
export type CameraState='idle'|'requesting'|'granted'|'denied'|'missing'|'busy'|'insecure'|'error'
export function useCamera(){
 const [state,setState]=useState<CameraState>('idle'),[permission,setPermission]=useState<PermissionState|undefined>(); const stream=useRef<MediaStream|null>(null)
 const stop=useCallback(()=>{stream.current?.getTracks().forEach(t=>t.stop());stream.current=null},[])
 const start=useCallback(async()=>{if(!window.isSecureContext){setState('insecure');return null}setState('requesting');try{const p=await navigator.permissions?.query({name:'camera' as PermissionName}).catch(()=>undefined);if(p)setPermission(p.state);const s=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});stream.current=s;setState('granted');return s}catch(e){const err=e as DOMException;setState(err.name==='NotAllowedError'?'denied':err.name==='NotFoundError'?'missing':err.name==='NotReadableError'?'busy':'error');return null}},[])
 useEffect(()=>()=>stop(),[stop]); return {state,permission,start,stop}
}
