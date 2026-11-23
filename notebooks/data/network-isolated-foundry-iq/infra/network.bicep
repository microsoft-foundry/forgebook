param location string
param prefix string
@secure()
param sshPublicKey string
param administrator string
param vmImageVersion string
param approvedFqdns array
param vnetPrefix string
param agentPrefix string
param pePrefix string
param adminPrefix string
param firewallPrefix string
param bastionPrefix string
param outsidePrefix string
param outsideSubnetPrefix string

resource firewallIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: '${prefix}-firewall-ip'
  location: location
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}
resource bastionIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: '${prefix}-bastion-ip'
  location: location
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}
resource lab 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${prefix}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: [vnetPrefix] }

  }
}
resource firewallSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: lab
  name: 'AzureFirewallSubnet'
  properties: { addressPrefix: firewallPrefix }
}
resource bastionSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: lab
  name: 'AzureBastionSubnet'
  properties: { addressPrefix: bastionPrefix }
  dependsOn: [firewallSubnet]
}
resource endpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: lab
  name: 'endpoints'
  properties: {
    addressPrefix: pePrefix
    privateEndpointNetworkPolicies: 'Disabled'
  }
  dependsOn: [bastionSubnet]
}
resource firewall 'Microsoft.Network/azureFirewalls@2024-05-01' = {
  name: '${prefix}-firewall'
  location: location
  properties: {
    sku: { name: 'AZFW_VNet'
 tier: 'Standard' }
    threatIntelMode: 'Alert'
    ipConfigurations: [{
      name: 'egress'
      properties: {
        subnet: { id: firewallSubnet.id }
        publicIPAddress: { id: firewallIp.id }
      }
    }]
    networkRuleCollections: [{
      name: 'entra'
      properties: {
        priority: 100
        action: { type: 'Allow' }
        rules: [{
          name: 'entra-https'
          protocols: ['TCP']
          sourceAddresses: [agentPrefix
 adminPrefix]
          destinationAddresses: ['AzureActiveDirectory']
          destinationPorts: ['443']
        }]
      }
    }]
    applicationRuleCollections: [{
      name: 'approved-platform-dependencies'
      properties: {
        priority: 200
        action: { type: 'Allow' }
        rules: [{
          name: 'reviewed-fqdns'
          sourceAddresses: [agentPrefix
 adminPrefix]
          protocols: [{ protocolType: 'Https'
 port: 443 }]
          targetFqdns: approvedFqdns
        }]
      }
    }]
  }
}
resource routes 'Microsoft.Network/routeTables@2024-05-01' = {
  name: '${prefix}-routes'
  location: location
  properties: {
    disableBgpRoutePropagation: true
    routes: [{
      name: 'default-to-firewall'
      properties: {
        addressPrefix: '0.0.0.0/0'
        nextHopType: 'VirtualAppliance'
        nextHopIpAddress: firewall.properties.ipConfigurations[0].properties.privateIPAddress
      }
    }]
  }
}
resource adminNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: '${prefix}-admin-nsg'
  location: location
  properties: {
    securityRules: [
      {
        name: 'BastionSSH'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: bastionPrefix
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '22'
        }
      }
      {
        name: 'DenyOtherInbound'
        properties: {
          priority: 200
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}
resource agents 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  dependsOn: [endpointSubnet]
  parent: lab
  name: 'agents'
  properties: {
    addressPrefix: agentPrefix
    defaultOutboundAccess: false
    routeTable: { id: routes.id }
    delegations: [{ name: 'agents'
 properties: { serviceName: 'Microsoft.App/environments' } }]
  }
}
resource admin 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: lab
  name: 'admin'
  properties: {
    addressPrefix: adminPrefix
    defaultOutboundAccess: false
    routeTable: { id: routes.id }
    networkSecurityGroup: { id: adminNsg.id }
  }
  dependsOn: [agents]
}
resource bastion 'Microsoft.Network/bastionHosts@2024-05-01' = {
  name: '${prefix}-bastion'
  location: location
  sku: { name: 'Basic' }
  properties: {
    ipConfigurations: [{
      name: 'bastion'
      properties: {
        subnet: { id: bastionSubnet.id }
        publicIPAddress: { id: bastionIp.id }
      }
    }]
  }
}
resource natIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: '${prefix}-outside-egress-ip'
  location: location
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}
resource nat 'Microsoft.Network/natGateways@2024-05-01' = {
  name: '${prefix}-outside-nat'
  location: location
  sku: { name: 'Standard' }
  properties: { publicIpAddresses: [{ id: natIp.id }] }
}
resource outside 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${prefix}-outside'
  location: location
  properties: {
    addressSpace: { addressPrefixes: [outsidePrefix] }
    subnets: [{
      name: 'runner'
      properties: {
        addressPrefix: outsideSubnetPrefix
        defaultOutboundAccess: false
        natGateway: { id: nat.id }
      }
    }]
  }
}
resource nics 'Microsoft.Network/networkInterfaces@2024-05-01' = [for (subnet, i) in [admin.id
 '${outside.id}/subnets/runner']: {
  name: '${prefix}-runner-${i}'
  location: location
  properties: {
    ipConfigurations: [{ name: 'private'
 properties: { privateIPAllocationMethod: 'Dynamic'
 subnet: { id: subnet } } }]
  }
}]
resource runners 'Microsoft.Compute/virtualMachines@2024-07-01' = [for i in range(0, 2): {
  name: '${prefix}-runner-${i}'
  location: location
  properties: {
    hardwareProfile: { vmSize: 'Standard_D2s_v5' }
    storageProfile: {
      imageReference: { publisher: 'Canonical'
 offer: 'ubuntu-24_04-lts'
 sku: 'server'
 version: vmImageVersion }
      osDisk: { createOption: 'FromImage'
 managedDisk: { storageAccountType: 'StandardSSD_LRS' }
 diskSizeGB: 32 }
    }
    osProfile: {
      computerName: '${prefix}-runner-${i}'
      adminUsername: administrator
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: { publicKeys: [{ path: '/home/${administrator}/.ssh/authorized_keys'
 keyData: sshPublicKey }] }
      }
    }
    networkProfile: { networkInterfaces: [{ id: nics[i].id }] }
  }
}]
output vnetId string = lab.id
output inventory object = {
  insideRunner: runners[0].id
  outsideRunner: runners[1].id
  firewall: firewall.id
  outsideNat: nat.id
  outsideVnet: outside.id
}
