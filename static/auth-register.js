function toggleProviderFields() {
  const role = document.getElementById('roleSelect').value;
  const consumerFields = document.getElementById('consumerFields');
  const providerFields = document.getElementById('providerFields');
  const providerServices = document.getElementById('providerServices');
  
  // Get consumer inputs
  const consumerPhone = document.querySelector('input[name="consumer_phone"]');
  const consumerPostcode = document.querySelector('input[name="consumer_postcode"]');
  
  // Get provider inputs
  const companyName = document.getElementById('companyName');
  const providerPhone = document.getElementById('providerPhone');
  const businessReg = document.getElementById('businessReg');
  const travelPostcodes = document.getElementById('travelPostcodes');
  
  if (role === 'provider') {
    // Show provider, hide consumer
    if (consumerFields) consumerFields.style.display = 'none';
    if (providerFields) providerFields.style.display = 'block';
    if (providerServices) providerServices.style.display = 'block';
    
    // Clear consumer fields
    if (consumerPhone) consumerPhone.value = '';
    if (consumerPostcode) consumerPostcode.value = '';
  } else {
    // Show consumer, hide provider
    if (consumerFields) consumerFields.style.display = 'block';
    if (providerFields) providerFields.style.display = 'none';
    if (providerServices) providerServices.style.display = 'none';
    
    // Clear provider fields
    if (companyName) companyName.value = '';
    if (providerPhone) providerPhone.value = '';
    if (businessReg) businessReg.value = '';
    if (travelPostcodes) travelPostcodes.value = '';
    document.querySelectorAll('input[name="service_categories"]').forEach(cb => cb.checked = false);
    document.getElementById('insuranceVerified').checked = false;
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
  const roleSelect = document.getElementById('roleSelect');
  if (roleSelect) {
    roleSelect.addEventListener('change', toggleProviderFields);
    toggleProviderFields();
  }
});
