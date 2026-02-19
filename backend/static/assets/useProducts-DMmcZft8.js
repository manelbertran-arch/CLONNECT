import{c as i,g as s,u as d,a as n,b as r,aB as c,e as a,aC as y,aD as p,aE as l}from"./index-D4HDx1pc.js";/**
 * @license lucide-react v0.462.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const P=i("BookOpen",[["path",{d:"M12 7v14",key:"1akyts"}],["path",{d:"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z",key:"ruj8y"}]]);function h(e=s()){return d({queryKey:a.products(e),queryFn:()=>c(e),staleTime:6e4})}function v(e=s()){const u=n();return r({mutationFn:t=>y(e,t),onSuccess:()=>{u.invalidateQueries({queryKey:a.products(e)}),u.invalidateQueries({queryKey:a.dashboard(e)})}})}function K(e=s()){const u=n();return r({mutationFn:({productId:t,product:o})=>p(e,t,o),onSuccess:()=>{u.invalidateQueries({queryKey:a.products(e)})}})}function Q(e=s()){const u=n();return r({mutationFn:t=>l(e,t),onSuccess:()=>{u.invalidateQueries({queryKey:a.products(e)}),u.invalidateQueries({queryKey:a.dashboard(e)})}})}export{P as B,v as a,K as b,Q as c,h as u};
