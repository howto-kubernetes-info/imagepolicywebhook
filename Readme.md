# Active Learning - imagePolicyWebhook
==Goal: CKS Certification==

Active learning is a learning style where learners engage with the material actively, through activities such as asking questions, participating in discussions, and applying the information they learn to real-world problems.
This approach emphasizes the learner's role in constructing their knowledge rather than passively receiving it from the teacher or the material.

Active learning is thought to promote deeper understanding, critical thinking, and retention of knowledge compared to passive approaches such as listening to lectures, reading textbooks or watching videos.

# Your Quest 
+ Write your own Kubernetes imagePolicyWebhook that allows only nginx images and images that uses the break glass mechanism in your cluster.
+ You can use the programming language of your choice. 
+ Run the webhook in your cluster and configure the Kubernetes apiserver to use it.
+ Use the cluster CA to sign your ssl keys.
+ Try to use only the offical Kubernetes documentation to solve the Kubernetes part of this quest.

### Start here
[ImagePolicyWebhook](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/#imagepolicywebhook)

[Certificate Signing Requests](https://kubernetes.io/docs/reference/access-authn-authz/certificate-signing-requests/)

# Example Solution
::: warning
WARNING!

The solution is only for education. Don't use this in production! 
You should use a policy engine like OPA or Kyverno in production.
:::

#
I only wrote a simple proof of concept webhook and this step by step guide to learn for the CKS certification.
I recommend that you do not use it. Instead, I encourage you to write your own webhook and documentation as part of your CKS certification journey. By attempting to solve this challenge on your own, you will gain a deeper understanding of the process.

If you encounter difficulties, you can refer to the following Documentation to use my imagePolicywebhook in a Kubernetes cluster.

## imagePolicyWebhook
An Image Policy Webhook is a type of webhook that can be used in Kubernetes clusters to enforce security policies on container images before they are deployed in a pod.

When a new pod is scheduled to run on a Kubernetes cluster, the Image Policy Webhook is triggered to evaluate the container image specified in the pod's configuration. The webhook checks if the image complies with any image whitelists or blacklists that have been defined.

If the image does not meet the defined security policies, the webhook can block the deployment of the pod, preventing any potential security risks from being introduced into the cluster.

Admission controller like the Image Policy Webhook are powerful tools for maintaining the security and integrity of Kubernetes clusters by providing a layer of checks before any code is deployed. 

At the end of this documentation, you run the python imagePolicyWebhook of this repository in your Kubernetes cluster. You can use a killercoda playground to test it.

[Killercoda](https://killercoda.com/playgrounds/scenario/kubernetes)

### Create a Namespace and a Service

First, we need to create a namespace for webhook and its service.
This is necessary because an internal DNS service address cannot be resolved by the apiserver, and we need to obtain the IP of the service to use it in a certificate signing request.

```
kubectl create ns imagepolicywebhook

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  creationTimestamp: null
  labels:
    app: imagepolicywebhook
  name: imagepolicywebhook
  namespace: imagepolicywebhook
spec:
  ports:
  - name: "443"
    port: 443
    protocol: TCP
    targetPort: 443
  selector:
    app: imagepolicywebhook
  type: ClusterIP
EOF
```

We create an environment variable for the IP to use it later.

```
export SERVICE_IP=$(kubectl get svc -n imagepolicywebhook -o jsonpath='{.items[0].spec.clusterIP}')

```

### Create Server Certificates

Now we create the key and a certificate signing request for the webhook server. Since we will use the kubelet-serving signer to sign this request, we need to provide a common name that starts with system:node, an organization name that is exactly system:nodes, the DNS name and the Service IP of our webhook.

Read more under [kubernetes-signers](https://kubernetes.io/docs/reference/access-authn-authz/certificate-signing-requests/#kubernetes-signers)
```
openssl genrsa -out webhook-server.key 2048
openssl req -new -key webhook-server.key -subj "/CN=system:node:imagepolicywebhook/O=system:nodes" -addext "subjectAltName = DNS:imagepolicywebhook.imagepolicywebhook.svc.cluster.local,DNS:imagepolicywebhook.imagepolicywebhook.svc,DNS:imagepolicywebhook.imagepolicywebhook.pod.cluster.local,IP:$SERVICE_IP" -out webhook-server.csr 
```
If you want to check the plain text of the csr, you can use the openssl command.
```
openssl req -in webhook-server.csr -text -noout
```

To use the csr in a Kubernetes manifest, we need to change the encoding to base64 and export it as an environment variable.
```
export SIGNING_REQUEST=$(cat webhook-server.csr | base64 | tr -d "\n")
```

We then send a CertificateSigningRequest manifest to the kube-apiserver to sign our certificate. The certificate usages in this manifest are the usages that the signer accept to sign.

```
cat <<EOF | kubectl apply -f -
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata:
  name: webhook-server
spec:
  request: $SIGNING_REQUEST
  signerName: kubernetes.io/kubelet-serving
  expirationSeconds: 864000  # ten days
  usages:
  - digital signature
  - key encipherment
  - server auth
EOF
```

This signing request is now ready to be approved. After approving it, we can write the signed certificate to a file.

```
kubectl get csr
kubectl certificate approve webhook-server
kubectl get csr webhook-server -o=jsonpath={.status.certificate} | base64 --decode > webhook-server.crt
```


### Create a secret with the certificates for the server
Our imagePolicyWebhook server will get the key and the certificate from a secret.

```
kubectl create secret tls webhook-server --cert=webhook-server.crt --key=webhook-server.key -n imagepolicywebhook
```

### Deploy the imagePolicyWebhook server

Now we have everything ready to run our imagePolicyWebhook as a deployment in the cluster. We need to mount the created key under /etc/ssl/private and our cert under /etc/ssl/certs/ into the pod.

```
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  creationTimestamp: null
  labels:
    app: imagepolicywebhook
  name: imagepolicywebhook
  namespace: imagepolicywebhook
spec:
  replicas: 1
  selector:
    matchLabels:
      app: imagepolicywebhook
  strategy: {}
  template:
    metadata:
      creationTimestamp: null
      labels:
        app: imagepolicywebhook
    spec:
      volumes:
      - name: cert
        secret:
          secretName: webhook-server
          items:
            - key: tls.crt
              path: webhook-server.crt 
      - name: key
        secret:
          secretName: webhook-server
          items:
            - key: tls.key
              path: webhook-server.key
      containers:
      - image: stephang/imagepolicywebhook:latest
        name: imagepolicywebhook
        ports:
        - containerPort: 443
        volumeMounts:
        - name: cert
          readOnly: true
          mountPath: /etc/ssl/certs/
        - name: key
          readOnly: true
          mountPath: /etc/ssl/private/
EOF

```
### Prepare the kube-apiserver configuration
To tell the kube-apiserver to use our webhook, it needs the server certificate, an admissionConfiguration and a kubeconfig to connect to the server. We provide the needed Data in the /etc/kubernetes/webhook directory.

```
mkdir -p /etc/kubernetes/webhook
cp webhook-server.crt /etc/kubernetes/webhook
```

The AdmissionConfiguration points to a kubeConfigfile that will authenticate the webhook. This configuration will allow every image in our cluster when the webhook is not reachable.

```
cat <<EOF >/etc/kubernetes/webhook/admissionConfig.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: AdmissionConfiguration
plugins:
  - name: ImagePolicyWebhook
    configuration:
      imagePolicy:
        kubeConfigFile: /etc/kubernetes/webhook/webhook.yaml
        allowTTL: 50
        denyTTL: 50
        retryBackoff: 500
        defaultAllow: true
EOF

```

The kube-apiserver uses only external DNS server and will not find the internal DNS service adresses. To let the apiserver use the internal service, the server in the kubeconfig must be set to the IP of the service. For standard admission controller, we could use a special notation to encode the dns name in the kubeconfig. As the client certificate, we use the existing apiserver certificate.
[ ](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/#authenticate-apiservers)

```
#/etc/kubernetes/webhook/webhook.yaml
cat <<EOF >/etc/kubernetes/webhook/webhook.yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority: /etc/kubernetes/webhook/webhook-server.crt
    server: https://$SERVICE_IP
  name: webhook
contexts:
- context:
    cluster: webhook
    user: imagepolicywebhook.imagepolicywebhook.svc
  name: webhook
current-context: webhook
kind: Config
users:
- name: imagepolicywebhook.imagepolicywebhook.svc
  user:
    client-certificate: /etc/kubernetes/pki/apiserver.crt
    client-key: /etc/kubernetes/pki/apiserver.key
EOF
```

### Prepare the kube-apiserver


To let the apiserver use our imagePolicyWebhook, we need to add two options and mount the Data into the apiserver pod.

```
# vim /etc/kubernetes/manifests/kube-apiserver.yaml
    - --enable-admission-plugins=ImagePolicyWebhook
    - --admission-control-config-file=/etc/kubernetes/webhook/admissionConfig.yaml

    volumeMounts:
    - mountPath: /etc/kubernetes/webhook
      name: webhook
      readOnly: true

  - hostPath:
      path: /etc/kubernetes/webhook/
      type: DirectoryOrCreate
    name: webhook
```

### Test the imagePolicyWebhook


To test the imagePolicyWebhook, we try to create a nginx pod. This should work.

```
kubectl run nginx --image nginx
```

When we try an alpine image, the webhook should refuse to run it. 

```
kubectl run alpine --image alpine
```

But an alpine pod with the right annotation should work.

```
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  creationTimestamp: null
  annotations:
    glasbreaker.image-policy.k8s.io/ticket-1234: "break-glass"
  labels:
    run: alpine
  name: alpine
spec:
  containers:
  - args:
    - sleep
    - 1d
    image: alpine
    name: alpine
    resources: {}
  dnsPolicy: ClusterFirst
  restartPolicy: Always
EOF
```

# Reflection
From my experience implementing an Image Policy Webhook in Kubernetes, I learned a lot about the technical details running my own admission controllers. Specifically, I gained an understanding of the process of creating certificates with OpenSSL and signing them with Kubernetes.

One interesting aspect that I encountered during the implementation process was the limitation of the Kubernetes API server in resolving internal DNS addresses. 

Overall, the experience of implementing an Image Policy Webhook in Kubernetes was a valuable learning opportunity for me.
